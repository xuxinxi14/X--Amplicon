"""
fastq_mergepairs.py
双端 FASTQ 序列合并工具。

这个文件是对 vsearch `fastq_mergepairs` 核心算法的纯 Python 重写。
目标不是做一个“差不多能用”的版本，而是尽量在默认参数、
重叠区评分、错配判定、质量合并和失败原因分类上与 vsearch 对齐。

算法来源：
- Edgar & Flyvbjerg (2015) 的质量校正公式
- vsearch 的重叠区评分与最佳对角线搜索逻辑

依赖：
- Python 标准库
- Biopython（仅用于读写 FASTQ）

当前已经实现的能力：
- 输入 R1 / R2 FASTQ，支持 `.fq` / `.fastq` / `.gz`
- 自动寻找最佳重叠区并合并为单条 FASTQ
- 支持长度过滤、N 碱基过滤、期望错误数过滤
- 支持 staggered 读段控制
- 返回结构化统计结果和失败原因明细

作为 Agent Tool 调用：
    from fastq_mergepairs import fastq_mergepairs

    result = fastq_mergepairs(
        read1_path="seq/KO1_1.fq.gz",
        read2_path="seq/KO1_2.fq.gz",
        output_path="temp/merged_python.fq",
        fastq_maxdiffs=10,
        fastq_minovlen=10,
        fastq_maxns=-1,
        fastq_maxee=1e308,
        allow_stagger=False,
    )

    print(result["merged"])

命令行调用：
    python fastq_mergepairs.py seq/KO1_1.fq.gz seq/KO1_2.fq.gz -o temp/merged_python.fq

16S 流程里常见的最简用法：
    python fastq_mergepairs.py seq/KO1_1.fq.gz seq/KO1_2.fq.gz ^
        -o temp/merged_python.fq

返回结果字段说明：
- `total`：输入 read pair 总数
- `merged`：成功合并的 read pair 数
- `not_merged`：未合并的 read pair 数
- `merge_rate`：合并率，范围 0.0 到 1.0
- `failed`：不同失败原因的计数字典

常见失败原因：
- `minlen`：截断后读段过短
- `maxlen`：读段过长
- `maxns`：N 碱基过多
- `minovlen`：重叠区过短
- `maxdiffs`：错配数过多
- `maxdiffpct`：错配比例过高
- `repeat`：存在多个高分重叠候选
- `staggered`：出现 staggered 读段但未允许
- `minscore`：最佳重叠得分仍然太低
- `nokmers`：没有足够的 k-mer 命中
- `maxee`：合并后期望错误数过高
"""

# ─────────────────────────────────────────────
# 1. 依赖导入
# ─────────────────────────────────────────────
import argparse
import gzip
import itertools
import math
import os
import sys
from typing import Dict, Iterator, List, Optional, Tuple


class RichHelpFormatter(
    argparse.ArgumentDefaultsHelpFormatter,
    argparse.RawTextHelpFormatter,
):
    """命令行帮助格式。

    这个格式类同时保留两件事：
    1. 自动显示默认值
    2. 保留多行示例的换行
    """

try:
    from Bio import SeqIO
    from Bio.SeqRecord import SeqRecord
except ImportError:
    sys.exit("错误：缺少 Biopython，请先运行 pip install biopython")

# ─────────────────────────────────────────────
# 2. 常量定义（与 vsearch 保持一致）
# ─────────────────────────────────────────────

# k-mer 长度，用于对角线预筛选（vsearch 固定为 5）
KMER_SIZE          = 5
# 同一对角线上最少 k-mer 命中数，才认为该对角线值得精细比对
MERGE_MINDIAGCOUNT = 4
# 重叠区最低比对得分（bits），低于此值认为比对不可靠
MERGE_MINSCORE     = 16.0
# 允许的最大得分下降（bits），超过则认为比对中途出现了大片错配
MERGE_DROPMAX      = 16.0
# 单碱基错配的最大惩罚上限（bits），防止极低质量碱基主导得分
MERGE_MISMATCHMAX  = -4.0

# Phred 质量值 ASCII 偏移（Sanger/Illumina 1.8+ 标准）
FASTQ_ASCII        = 33

# 互补碱基映射表（用于 reverse complement）
COMPLEMENT = str.maketrans("ACGTacgtNn", "TGCAtgcaNn")


# ─────────────────────────────────────────────
# 3. 质量值预计算
# ─────────────────────────────────────────────

def _q_to_p(phred: int) -> float:
    """
    Phred 质量值 → 错误概率。
    公式：p = 10^(-Q/10)
    Q < 2 时返回 0.75（极低质量，最大不确定性）。
    """
    if phred < 2:
        return 0.75
    return 10.0 ** (-phred / 10.0)


def _precompute_tables(
    fastq_qmin: int,
    fastq_qmax: int,
    fastq_qminout: int,
    fastq_qmaxout: int,
) -> Tuple[
    Dict[Tuple[int, int], int],    # merge_qual_same：两碱基匹配时的合并质量 ASCII 码
    Dict[Tuple[int, int], int],    # merge_qual_diff：两碱基错配时的合并质量 ASCII 码
    Dict[Tuple[int, int], float],  # match_score：匹配得分（bits）
    Dict[Tuple[int, int], float],  # mism_score：错配得分（bits）
    Dict[int, float],              # q2p：ASCII 码 → 错误概率
]:
    """
    预计算所有质量值组合的合并质量和比对得分。
    基于 Edgar & Flyvbjerg (2015) 的贝叶斯质量校正公式。
    """
    merge_qual_same: Dict[Tuple[int, int], int]   = {}
    merge_qual_diff: Dict[Tuple[int, int], int]   = {}
    match_score:     Dict[Tuple[int, int], float] = {}
    mism_score:      Dict[Tuple[int, int], float] = {}
    q2p:             Dict[int, float]             = {}

    for ascii_x in range(33, 127):
        phred_x = ascii_x - FASTQ_ASCII
        px = _q_to_p(phred_x)
        q2p[ascii_x] = px

        for ascii_y in range(33, 127):
            phred_y = ascii_y - FASTQ_ASCII
            py = _q_to_p(phred_y)

            # ── 匹配时的合并质量（Edgar & Flyvbjerg 公式）──
            # 两条读段碱基相同，计算"真正匹配"的后验错误概率
            denom_same = 1.0 - px - py + 4.0 * px * py / 3.0
            denom_same = denom_same if denom_same > 0 else 1e-300
            p_same = (px * py / 3.0) / denom_same
            p_same = max(p_same, 1e-300)
            q_same = round(-10.0 * math.log10(p_same))
            q_same = min(max(q_same, fastq_qminout), fastq_qmaxout)
            merge_qual_same[(ascii_x, ascii_y)] = FASTQ_ASCII + int(q_same)

            # ── 错配时的合并质量（选质量较高的碱基，x 为高质量方）──
            denom_diff = px + py - 4.0 * px * py / 3.0
            denom_diff = denom_diff if denom_diff > 0 else 1e-300
            p_diff = px * (1.0 - py / 3.0) / denom_diff
            p_diff = max(p_diff, 1e-300)
            q_diff = round(-10.0 * math.log10(p_diff))
            q_diff = min(max(q_diff, fastq_qminout), fastq_qmaxout)
            merge_qual_diff[(ascii_x, ascii_y)] = FASTQ_ASCII + int(q_diff)

            # ── 比对打分（log-odds，单位 bits）──
            # 观测到匹配的概率
            p_match = 1.0 - px - py + (px * py * 4.0 / 3.0)
            p_match = max(p_match, 1e-300)
            match_score[(ascii_x, ascii_y)] = math.log2(p_match / 0.25)

            # 观测到错配的概率，取最大惩罚上限
            p_mism = max(1.0 - p_match, 1e-300)
            mism_score[(ascii_x, ascii_y)] = min(math.log2(p_mism / 0.75), MERGE_MISMATCHMAX)

    return merge_qual_same, merge_qual_diff, match_score, mism_score, q2p


# ─────────────────────────────────────────────
# 4. 辅助函数
# ─────────────────────────────────────────────

def _open_fastq(path: str):
    """自动识别 .gz 压缩，返回文本模式文件句柄。"""
    if not os.path.isfile(path):
        raise FileNotFoundError(f"错误：找不到文件 '{path}'")
    if path.endswith(".gz"):
        return gzip.open(path, "rt", encoding="utf-8")
    return open(path, "r", encoding="utf-8")


def _open_fastq_write(path: str):
    """打开输出文件，自动处理 .gz 压缩。"""
    if path.endswith(".gz"):
        return gzip.open(path, "wt", encoding="utf-8")
    return open(path, "w", encoding="utf-8")


def _truncate_by_quality(qual_str: str, truncqual: int) -> int:
    """
    按质量截断：找到第一个 Phred ≤ truncqual 的位置，返回截断后长度。
    truncqual = -1 表示不截断（vsearch 默认行为）。
    """
    if truncqual < 0:
        return len(qual_str)
    for i, qc in enumerate(qual_str):
        phred = ord(qc) - FASTQ_ASCII
        if phred <= truncqual:
            return i
    return len(qual_str)


def _build_kmer_diag_counts(
    fwd_seq: str,
    fwd_len: int,
    rev_seq: str,
    rev_len: int,
    k: int,
) -> List[int]:
    """
    k-mer 对角线计数，严格对应 vsearch 的 kh_insert_kmers + kh_find_diagonals 逻辑。

    vsearch 的做法：
      - kh_insert_kmers：对 fwd 序列建立 k-mer → 位置(fwd_pos) 的索引
      - kh_find_diagonals：在原始 rev 序列（未取反向互补）上滑动 k-mer，
        取其互补后查 fwd 索引，命中时计算对角线编号

    对角线编号定义（与 optimize() 中 diag = rev_len + fwd_len - i 对应）：
      diag = fwd_pos + (rev_len - rev_pos)
           = fwd_len + rev_len - (fwd_len - fwd_pos + rev_pos)
      其中 i = fwd_len - fwd_pos + rev_pos（表示偏移量 offset）

    这里 rev_pos 是 rev 原始序列上的位置（从 0 到 rev_len-1），
    k-mer 取互补后与 fwd 做匹配。

    返回长度为 fwd_len + rev_len 的列表，索引为对角线编号。
    """
    total_len = fwd_len + rev_len
    diag_counts = [0] * total_len

    # 对 fwd 建立 k-mer 索引：k-mer = fwd[p], fwd[p-1], ..., fwd[p-k+1]（从 p 往左 k 个）
    # 这与 vsearch kh_insert_kmers 一致：fwd 从右往左遍历，k-mer 以 p 为末端位置
    fwd_kmers: Dict[str, List[int]] = {}
    for p in range(k - 1, fwd_len):
        # 反向 k-mer：fwd_seq[p..p-k+1]（倒序）
        km = fwd_seq[p:p - k:-1]   # Python 切片：从 p 到 p-k（不含），步长 -1
        if 'N' not in km:
            fwd_kmers.setdefault(km, []).append(p)

    # 在原始 rev 序列上滑动，取正向 k-mer 互补后与 fwd 反向 k-mer 匹配
    # 对应 vsearch kh_find_diagonals：rev[q:q+k] 互补后查 fwd 反向 k-mer 索引
    for q in range(rev_len - k + 1):
        km_rev = rev_seq[q:q + k]
        if 'N' in km_rev:
            continue
        # 互补（不反转）
        km_comp = km_rev.translate(COMPLEMENT)

        if km_comp in fwd_kmers:
            for p in fwd_kmers[km_comp]:
                # 命中时：fwd[p] 对应 rev[q]（比对中第一个碱基对）
                # 根据比对循环：fp+rp = fwd_pos_start + rev_pos_start（常数）
                # 对于该对角线 diag = fwd_len + rev_len - i，满足 fp+rp = diag-1
                # 所以 diag = p + q + 1
                diag = p + q + 1
                if 0 <= diag < total_len:
                    diag_counts[diag] += 1

    return diag_counts


def _merge_sym(
    fwd_sym: str, rev_sym: str,
    fwd_qual_ascii: int, rev_qual_ascii: int,
    merge_qual_same: Dict[Tuple[int, int], int],
    merge_qual_diff: Dict[Tuple[int, int], int],
) -> Tuple[str, int]:
    """
    合并单个碱基位置的碱基和质量值。

    规则（与 vsearch merge_sym 一致）：
      - 任一方为 N：取另一方的碱基和质量
      - 两方碱基相同（匹配）：用 merge_qual_same 公式提升质量
      - 两方碱基不同（错配）：取质量较高方的碱基，用 merge_qual_diff 公式降低质量

    返回：(合并碱基, 合并质量 ASCII 码)
    """
    if rev_sym == 'N':
        return fwd_sym, fwd_qual_ascii
    if fwd_sym == 'N':
        return rev_sym, rev_qual_ascii

    if fwd_sym == rev_sym:
        # 匹配：质量提升
        merged_qual = merge_qual_same.get(
            (fwd_qual_ascii, rev_qual_ascii),
            fwd_qual_ascii
        )
        return fwd_sym, merged_qual
    else:
        # 错配：取质量高的碱基，质量降低
        # C++ 用严格大于 (>)，质量相等时取 rev 碱基
        if fwd_qual_ascii > rev_qual_ascii:
            merged_qual = merge_qual_diff.get(
                (fwd_qual_ascii, rev_qual_ascii),
                fwd_qual_ascii
            )
            return fwd_sym, merged_qual
        else:
            merged_qual = merge_qual_diff.get(
                (rev_qual_ascii, fwd_qual_ascii),
                rev_qual_ascii
            )
            return rev_sym, merged_qual


def _find_best_overlap(
    fwd_seq: str, fwd_qual: str, fwd_len: int,
    rev_seq: str, rev_qual: str, rev_len: int,
    match_score: Dict[Tuple[int, int], float],
    mism_score:  Dict[Tuple[int, int], float],
    fastq_maxdiffs: int,
    fastq_maxdiffpct: float,
    fastq_minovlen: int,
    fastq_minmergelen: int,
    fastq_maxmergelen: int,
    allow_stagger: bool,
    merge_mindiagcount: int,
    merge_minscore: float,
) -> Tuple[int, str]:
    """
    寻找最佳重叠偏移量（offset = i，即 fwd_len + rev_len - merged_len）。

    严格对应 vsearch optimize() 函数：
      - fwd_pos 从右端往左遍历（--fwd_pos）
      - rev_pos 从起始位置往左遍历（--rev_pos），对碱基实时取互补
      - 对角线：diag = rev_len + fwd_len - i
      - rev_pos_start = rev_len - 1 - rev_3prime_overhang

    返回：(best_i, 失败原因字符串)
    """
    # 对角线范围：i 从 1 到 fwd_len + rev_len - 1
    i1 = 1
    i2 = fwd_len + rev_len - 1

    # 计算 k-mer 对角线命中数（用原始 rev 序列，不反转）
    diag_counts = _build_kmer_diag_counts(fwd_seq, fwd_len, rev_seq, rev_len, KMER_SIZE)

    best_score  = 0.0
    best_i      = 0
    best_diffs  = 0
    hits        = 0   # 得分超过阈值的候选数（>1 则为重复）
    kmers_found = 0   # 是否找到任何 k-mer 命中

    for i in range(i1, i2 + 1):
        # 对角线索引（与 vsearch 中 diag = rev_trunc + fwd_trunc - i 完全一致）
        diag = rev_len + fwd_len - i
        if diag < 0 or diag >= len(diag_counts):
            continue
        if diag_counts[diag] < merge_mindiagcount:
            continue

        kmers_found = 1

        # 计算该偏移下的重叠区范围（与 C++ 完全一致）
        fwd_3prime_overhang = i - rev_len if i > rev_len else 0
        rev_3prime_overhang = i - fwd_len if i > fwd_len else 0
        overlap = i - fwd_3prime_overhang - rev_3prime_overhang

        if overlap <= 0:
            continue

        # fwd 起始位置（从右端往左，--fwd_pos）
        fwd_pos_start = fwd_len - fwd_3prime_overhang - 1
        # rev 起始位置（从左往右，++rev_pos），对应 C++：rev_trunc - rev_3prime_overhang - overlap
        rev_pos_start = rev_len - rev_3prime_overhang - overlap

        score      = 0.0
        score_high = 0.0
        dropmax    = 0.0
        diffs      = 0

        fwd_pos = fwd_pos_start
        rev_pos = rev_pos_start

        for _ in range(overlap):
            fwd_b = fwd_seq[fwd_pos]
            # rev 碱基取互补（对应 C++ 的 map_complement，不反转序列方向）
            rev_b_raw = rev_seq[rev_pos]
            rev_b = rev_b_raw.translate(COMPLEMENT)

            fwd_q = ord(fwd_qual[fwd_pos])
            rev_q = ord(rev_qual[rev_pos])

            # fwd 往左（--fwd_pos），rev 往右（++rev_pos）
            fwd_pos -= 1
            rev_pos += 1

            if fwd_b == rev_b:
                score += match_score.get((fwd_q, rev_q), 0.0)
                if score > score_high:
                    score_high = score
            else:
                score += mism_score.get((fwd_q, rev_q), MERGE_MISMATCHMAX)
                diffs += 1
                drop = score_high - score
                if drop > dropmax:
                    dropmax = drop

        # 得分下降过大，认为比对不可靠，清零
        if dropmax >= MERGE_DROPMAX:
            score = 0.0

        if score >= merge_minscore:
            hits += 1

        if score > best_score:
            best_score = score
            best_i     = i
            best_diffs = diffs

    # ── 过滤判断（顺序与 vsearch optimize() 完全一致）──

    if hits > 1:
        return 0, "repeat"

    if (not allow_stagger) and best_i > fwd_len:
        return 0, "staggered"

    if best_diffs > fastq_maxdiffs:
        return 0, "maxdiffs"

    # C++ 第843行：100.0 * best_diffs / best_i（分母是 best_i，不是 overlap）
    if best_i > 0 and (100.0 * best_diffs / best_i) > fastq_maxdiffpct:
        return 0, "maxdiffpct"

    if kmers_found == 0:
        return 0, "nokmers"

    if best_score < merge_minscore:
        return 0, "minscore"

    if best_i < fastq_minovlen:
        return 0, "minovlen"

    merged_len = fwd_len + rev_len - best_i
    if merged_len < fastq_minmergelen:
        return 0, "minmergelen"
    if merged_len > fastq_maxmergelen:
        return 0, "maxmergelen"

    return best_i, ""


def _do_merge(
    fwd_seq: str, fwd_qual: str, fwd_len: int,
    rev_seq: str, rev_qual: str, rev_len: int,
    offset: int,
    merge_qual_same: Dict[Tuple[int, int], int],
    merge_qual_diff: Dict[Tuple[int, int], int],
    q2p: Dict[int, float],
    fastq_maxee: float,
) -> Tuple[Optional[str], Optional[str], float, float, float, int, int, str]:
    """
    执行实际的序列合并，生成合并序列和质量字符串。

    结构（offset = i = fwd_len + rev_len - merged_len）：
      [fwd 5'端独有区] [重叠区（fwd+rev 合并）] [rev 5'端独有区]

    返回：
      (merged_seq, merged_qual, ee_merged, ee_fwd, ee_rev,
       fwd_errors, rev_errors, 失败原因)
    """
    # fwd 5' 端独有区长度（对应 C++ 的 fwd_5prime_overhang）
    fwd_5prime_overhang = fwd_len - offset if fwd_len > offset else 0
    # rev 3' 端超出 fwd 的部分（stagger 时存在）
    rev_3prime_overhang = offset - fwd_len if offset > fwd_len else 0

    merged_seq  = []
    merged_qual = []
    ee_merged   = 0.0
    ee_fwd      = 0.0
    ee_rev      = 0.0
    fwd_errors  = 0
    rev_errors  = 0

    # 阶段 1：fwd 5' 端独有区（直接复制 fwd[0..fwd_5prime_overhang-1]）
    # 对应 C++ merge() 第一段 while (fwd_pos < fwd_5prime_overhang)
    for fwd_pos in range(fwd_5prime_overhang):
        sym  = fwd_seq[fwd_pos]
        qual = ord(fwd_qual[fwd_pos])
        merged_seq.append(sym)
        merged_qual.append(chr(qual))
        ee = q2p.get(qual, 0.0)
        ee_merged += ee
        ee_fwd    += ee

    # 阶段 2：重叠区
    # 对应 C++ merge()：rev_pos = rev_trunc - 1 - rev_3prime_overhang，然后 --rev_pos
    # fwd 从 fwd_5prime_overhang 往右（++fwd_pos），rev 从右往左（--rev_pos）
    fwd_pos = fwd_5prime_overhang
    rev_pos = rev_len - 1 - rev_3prime_overhang

    while fwd_pos < fwd_len and rev_pos >= 0:
        fwd_b = fwd_seq[fwd_pos]
        # 对应 C++ 的 map_complement(rev_sequence[rev_pos])
        rev_b = rev_seq[rev_pos].translate(COMPLEMENT)
        fwd_q = ord(fwd_qual[fwd_pos])
        rev_q = ord(rev_qual[rev_pos])

        # 低质量碱基（质量字符 ASCII < 33+2=35，即 Phred < 2）视为 N
        # 对应 C++ 的：fwd_qual < 2 ? 'N' : fwd_sym
        # 注意 C++ 中 fwd_qual 是 ASCII 字符，直接与整数 2 比较，相当于 Phred < 2 - 33 = -31
        # 即：只要质量字符 ASCII < 2 才为 N（实际上不可能，所以 C++ 这个条件几乎永不触发）
        # 保持与 C++ 一致：
        fwd_effective = 'N' if fwd_q < 2 else fwd_b
        rev_effective = 'N' if rev_q < 2 else rev_b

        sym, qual_ascii = _merge_sym(
            fwd_effective, rev_effective,
            fwd_q, rev_q,
            merge_qual_same, merge_qual_diff,
        )

        if sym != fwd_b:
            fwd_errors += 1
        if sym != rev_b:
            rev_errors += 1

        merged_seq.append(sym)
        merged_qual.append(chr(qual_ascii))
        ee_merged += q2p.get(qual_ascii, 0.0)
        ee_fwd    += q2p.get(fwd_q, 0.0)
        ee_rev    += q2p.get(rev_q, 0.0)

        fwd_pos += 1
        rev_pos -= 1  # 对应 C++ 的 --rev_pos

    # 阶段 3：rev 5' 端独有区（rev 剩余部分，继续往左取互补）
    # 对应 C++ 的 while (rev_pos >= 0)
    while rev_pos >= 0:
        sym  = rev_seq[rev_pos].translate(COMPLEMENT)
        qual = ord(rev_qual[rev_pos])
        merged_seq.append(sym)
        merged_qual.append(chr(qual))
        ee = q2p.get(qual, 0.0)
        ee_merged += ee
        ee_rev    += ee
        rev_pos   -= 1

    # 检查期望错误数过滤
    if ee_merged > fastq_maxee:
        return None, None, ee_merged, ee_fwd, ee_rev, fwd_errors, rev_errors, "maxee"

    return (
        "".join(merged_seq),
        "".join(merged_qual),
        ee_merged, ee_fwd, ee_rev,
        fwd_errors, rev_errors,
        "",
    )


# ─────────────────────────────────────────────
# 5. 主函数（Agent Tool 接口）
# ─────────────────────────────────────────────

def fastq_mergepairs(
    read1_path: str,
    read2_path: str,
    output_path: str,
    # ── 过滤参数（与 vsearch 默认值一致）──
    fastq_maxdiffs:    int   = 10,      # 重叠区允许的最大错配碱基数（vsearch 默认 10）
    fastq_pctid:       float = 0.0,     # 重叠区最低相似度百分比（0=不过滤）
    fastq_minovlen:    int   = 10,      # 最小重叠长度（vsearch 默认 10）
    fastq_minmergelen: int   = 0,       # 合并后序列最小长度（0=不过滤）
    fastq_maxmergelen: int   = 1000000, # 合并后序列最大长度
    fastq_trunctail:   int   = -1,      # 按质量截断阈值（-1=不截断）
    fastq_qmin:        int   = 0,       # 输入质量值最小值
    fastq_qmax:        int   = 41,      # 输入质量值最大值
    fastq_qminout:     int   = 0,       # 输出质量值最小值
    fastq_qmaxout:     int   = 41,      # 输出质量值最大值
    fastq_minlen:      int   = 1,       # 输入读段最小长度
    fastq_maxlen:      int   = 1000000, # 输入读段最大长度
    fastq_maxns:       int   = -1,      # 允许的最大 N 碱基数（-1=不过滤，vsearch 默认行为）
    fastq_maxee:       float = 1e308,   # 合并序列最大期望错误数（不过滤）
    allow_stagger:     bool  = False,   # 是否允许 staggered 读段对
) -> Dict:
    """
    双端 FASTQ 序列合并（vsearch fastq_mergepairs 算法）。

    参数：
        read1_path    : R1（正向）FASTQ 文件路径，支持 .fq / .fq.gz
        read2_path    : R2（反向）FASTQ 文件路径，支持 .fq / .fq.gz
        output_path   : 合并结果输出路径，支持 .fq / .fq.gz
        fastq_maxdiffs: 重叠区最大错配数（默认 10）
        fastq_pctid   : 重叠区最低相似度 % （默认 0，即不过滤）
        fastq_minovlen: 最小重叠长度（默认 10）
        fastq_minmergelen: 合并序列最小长度（默认 0）
        fastq_maxmergelen: 合并序列最大长度（默认 1000000）
        fastq_trunctail: 质量截断阈值，≤该值则截断（默认 -1 不截断）
        fastq_qmin/qmax: 输入质量值范围（默认 0-41）
        fastq_qminout/qmaxout: 输出质量值范围（默认 0-41）
        fastq_minlen  : 输入读段最小长度（默认 1）
        fastq_maxlen  : 输入读段最大长度（默认 1000000）
        fastq_maxns   : 允许的最大 N 数（默认 -1，即不过滤）
        fastq_maxee   : 合并序列最大期望错误数（默认不过滤）
        allow_stagger : 是否允许 staggered 读段对（默认 False）

    返回字典：
        {
          "total":        总读段对数,
          "merged":       成功合并数,
          "not_merged":   未合并数,
          "merge_rate":   合并率（0.0-1.0）,
          "failed": {
            "minlen":       读段过短,
            "maxlen":       读段过长,
            "maxns":        N 碱基过多,
            "minovlen":     重叠区过短,
            "maxdiffs":     错配数过多,
            "maxdiffpct":   错配比例过高,
            "staggered":    staggered 读段对,
            "repeat":       多重比对（重复序列）,
            "minscore":     比对得分过低,
            "nokmers":      无 k-mer 命中,
            "minmergelen":  合并序列过短,
            "maxmergelen":  合并序列过长,
            "maxee":        期望错误数过高,
            "undefined":    未知原因,
          }
        }
    """
    # ── 参数校验 ──
    if not os.path.isfile(read1_path):
        raise FileNotFoundError(f"错误：R1 文件不存在 '{read1_path}'")
    if not os.path.isfile(read2_path):
        raise FileNotFoundError(f"错误：R2 文件不存在 '{read2_path}'")
    if fastq_minovlen < 5:
        raise ValueError("错误：fastq_minovlen 最小值为 5")
    if fastq_maxdiffs < 0:
        raise ValueError("错误：fastq_maxdiffs 不能为负数")
    if not (0.0 <= fastq_pctid <= 100.0):
        raise ValueError("错误：fastq_pctid 必须在 0-100 之间")
    if fastq_qmin < 0 or fastq_qmax > 93 or fastq_qmin > fastq_qmax:
        raise ValueError("错误：fastq_qmin/qmax 范围无效（应在 0-93 且 qmin ≤ qmax）")

    # 短重叠时放宽内部阈值（与 vsearch 一致）
    merge_mindiagcount = MERGE_MINDIAGCOUNT
    merge_minscore     = MERGE_MINSCORE
    if fastq_minovlen < 9:
        merge_mindiagcount = fastq_minovlen - 4
        merge_minscore     = 1.6 * fastq_minovlen

    # fastq_pctid → maxdiffpct（vsearch 内部用 maxdiffpct）
    fastq_maxdiffpct = 100.0 - fastq_pctid

    # ── 预计算质量表 ──
    merge_qual_same, merge_qual_diff, match_score, mism_score, q2p = \
        _precompute_tables(fastq_qmin, fastq_qmax, fastq_qminout, fastq_qmaxout)

    # ── 统计计数器 ──
    total   = 0
    merged  = 0
    failed: Dict[str, int] = {
        "minlen": 0, "maxlen": 0, "maxns": 0,
        "minovlen": 0, "maxdiffs": 0, "maxdiffpct": 0,
        "staggered": 0, "repeat": 0, "minscore": 0,
        "nokmers": 0, "minmergelen": 0, "maxmergelen": 0,
        "maxee": 0, "undefined": 0,
    }

    # ── 打开输入/输出文件 ──
    fh_out = _open_fastq_write(output_path)

    try:
        with _open_fastq(read1_path) as fh1, _open_fastq(read2_path) as fh2:
            r1_iter = SeqIO.parse(fh1, "fastq")
            r2_iter = SeqIO.parse(fh2, "fastq")

            for rec1, rec2 in itertools.zip_longest(r1_iter, r2_iter, fillvalue=None):
                if rec1 is None or rec2 is None:
                    raise ValueError(f"错误：R1 和 R2 文件长度不匹配，在记录 {total} 处中断")
                total += 1
                reason = ""  # 失败原因，空字符串表示成功

                # ── 读取序列和质量字符串 ──
                fwd_seq  = str(rec1.seq).upper()
                rev_seq  = str(rec2.seq).upper()
                # Biopython 的 letter_annotations["phred_quality"] 是整数列表
                # 转回 ASCII 字符串以便与预计算表索引一致
                fwd_qual = "".join(chr(q + FASTQ_ASCII) for q in rec1.letter_annotations["phred_quality"])
                rev_qual = "".join(chr(q + FASTQ_ASCII) for q in rec2.letter_annotations["phred_quality"])

                fwd_len = len(fwd_seq)
                rev_len = len(rev_seq)

                # ── 长度过滤 ──
                if fwd_len < fastq_minlen or rev_len < fastq_minlen:
                    reason = "minlen"
                elif fwd_len > fastq_maxlen or rev_len > fastq_maxlen:
                    reason = "maxlen"

                # ── 质量截断（fastq_trunctail）──
                if not reason:
                    fwd_trunc = _truncate_by_quality(fwd_qual, fastq_trunctail)
                    rev_trunc = _truncate_by_quality(rev_qual, fastq_trunctail)
                    if fwd_trunc < fastq_minlen or rev_trunc < fastq_minlen:
                        reason = "minlen"
                    else:
                        # 截断后的有效序列和质量
                        fwd_seq  = fwd_seq[:fwd_trunc]
                        fwd_qual = fwd_qual[:fwd_trunc]
                        rev_seq  = rev_seq[:rev_trunc]
                        rev_qual = rev_qual[:rev_trunc]
                        fwd_len  = fwd_trunc
                        rev_len  = rev_trunc

                # ── N 碱基过滤 + 将 N 的质量置为最低（ASCII 33 = Phred 0）──
                if not reason:
                    # fastq_maxns < 0 时不进行 N 碱基过滤（vsearch 默认行为）
                    if fastq_maxns >= 0:
                        fwd_ncount = fwd_seq.count('N')
                        rev_ncount = rev_seq.count('N')
                        if fwd_ncount > fastq_maxns or rev_ncount > fastq_maxns:
                            reason = "maxns"

                    if not reason:
                        # 将 N 位置的质量值设为 ASCII 33（Phred 0），
                        # 使其在合并时被视为低质量碱基
                        fwd_qual_list = list(fwd_qual)
                        for i, b in enumerate(fwd_seq):
                            if b == 'N':
                                fwd_qual_list[i] = chr(FASTQ_ASCII)
                        fwd_qual = "".join(fwd_qual_list)

                        rev_qual_list = list(rev_qual)
                        for i, b in enumerate(rev_seq):
                            if b == 'N':
                                rev_qual_list[i] = chr(FASTQ_ASCII)
                        rev_qual = "".join(rev_qual_list)

                # ── 寻找最佳重叠 ──
                offset = 0
                if not reason:
                    offset, reason = _find_best_overlap(
                        fwd_seq, fwd_qual, fwd_len,
                        rev_seq, rev_qual, rev_len,
                        match_score, mism_score,
                        fastq_maxdiffs, fastq_maxdiffpct,
                        fastq_minovlen, fastq_minmergelen, fastq_maxmergelen,
                        allow_stagger,
                        merge_mindiagcount, merge_minscore,
                    )

                # ── 执行合并 ──
                if not reason and offset > 0:
                    merged_seq, merged_qual, _, _, _, _, _, fail = _do_merge(
                        fwd_seq, fwd_qual, fwd_len,
                        rev_seq, rev_qual, rev_len,
                        offset,
                        merge_qual_same, merge_qual_diff,
                        q2p, fastq_maxee,
                    )
                    if fail:
                        reason = fail
                    else:
                        # ── 写出合并结果 ──
                        merged += 1
                        header = rec1.id
                        fh_out.write(f"@{header}\n{merged_seq}\n+\n{merged_qual}\n")

                # ── 统计失败原因 ──
                if reason:
                    if reason in failed:
                        failed[reason] += 1
                    else:
                        failed["undefined"] += 1

    finally:
        fh_out.close()

    not_merged = total - merged
    merge_rate = merged / total if total > 0 else 0.0

    return {
        "total":      total,
        "merged":     merged,
        "not_merged": not_merged,
        "merge_rate": round(merge_rate, 4),
        "failed":     failed,
    }


# ─────────────────────────────────────────────
# 6. 命令行入口
# ─────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "双端 FASTQ 序列合并工具（vsearch fastq_mergepairs 算法 Python 实现）。\n"
            "支持重叠区搜索、质量加权合并、失败原因统计，以及 gzip 输入输出。"
        ),
        epilog=(
            "命令行示例：\n"
            "  python fastq_mergepairs.py seq/KO1_1.fq.gz seq/KO1_2.fq.gz "
            "-o temp/merged_python.fq\n\n"
            "常用参数说明：\n"
            "  --fastq_maxns -1 表示不过滤 N 碱基，这是 vsearch 默认行为\n"
            "  --fastq_pctid 0 表示不按相似度过滤\n"
            "  --fastq_trunctail -1 表示不做质量截断\n"
            "  --allow_stagger 打开后允许 staggered 读段对通过"
        ),
        formatter_class=RichHelpFormatter,
    )
    p.add_argument(
        "read1",
        help="R1 正向 FASTQ 文件，支持 .fq / .fastq / .gz",
    )
    p.add_argument(
        "read2",
        help="R2 反向 FASTQ 文件，支持 .fq / .fastq / .gz",
    )
    p.add_argument(
        "-o",
        "--output",
        required=True,
        help="合并结果输出 FASTQ 文件，支持 .fq / .fastq / .gz",
    )
    p.add_argument(
        "--fastq_maxdiffs",
        type=int,
        default=10,
        help="重叠区允许的最大错配碱基数",
    )
    p.add_argument(
        "--fastq_pctid",
        type=float,
        default=0.0,
        help="重叠区最低相似度百分比，0 表示不启用这个过滤",
    )
    p.add_argument(
        "--fastq_minovlen",
        type=int,
        default=10,
        help="最小重叠长度，代码要求不能小于 5",
    )
    p.add_argument(
        "--fastq_minmergelen",
        type=int,
        default=0,
        help="合并后序列允许的最小长度，0 表示不限制",
    )
    p.add_argument(
        "--fastq_maxmergelen",
        type=int,
        default=1000000,
        help="合并后序列允许的最大长度",
    )
    p.add_argument(
        "--fastq_trunctail",
        type=int,
        default=-1,
        help="按质量截断的阈值，Phred <= 该值时从该位截断，-1 表示不截断",
    )
    p.add_argument(
        "--fastq_qmin",
        type=int,
        default=0,
        help="输入质量值最小值",
    )
    p.add_argument(
        "--fastq_qmax",
        type=int,
        default=41,
        help="输入质量值最大值",
    )
    p.add_argument(
        "--fastq_qminout",
        type=int,
        default=0,
        help="输出质量值最小值",
    )
    p.add_argument(
        "--fastq_qmaxout",
        type=int,
        default=41,
        help="输出质量值最大值",
    )
    p.add_argument(
        "--fastq_minlen",
        type=int,
        default=1,
        help="输入读段最小长度，截断前后都会检查",
    )
    p.add_argument(
        "--fastq_maxlen",
        type=int,
        default=1000000,
        help="输入读段最大长度",
    )
    p.add_argument(
        "--fastq_maxns",
        type=int,
        default=-1,
        help="允许的最大 N 碱基数，-1 表示不过滤，和 vsearch 默认一致",
    )
    p.add_argument(
        "--fastq_maxee",
        type=float,
        default=1e308,
        help="合并后序列允许的最大期望错误数，默认等于基本不过滤",
    )
    p.add_argument(
        "--allow_stagger",
        action="store_true",
        help="允许 staggered 读段对通过过滤",
    )
    return p


def main():
    parser = _build_parser()
    args   = parser.parse_args()

    try:
        result = fastq_mergepairs(
            read1_path        = args.read1,
            read2_path        = args.read2,
            output_path       = args.output,
            fastq_maxdiffs    = args.fastq_maxdiffs,
            fastq_pctid       = args.fastq_pctid,
            fastq_minovlen    = args.fastq_minovlen,
            fastq_minmergelen = args.fastq_minmergelen,
            fastq_maxmergelen = args.fastq_maxmergelen,
            fastq_trunctail   = args.fastq_trunctail,
            fastq_qmin        = args.fastq_qmin,
            fastq_qmax        = args.fastq_qmax,
            fastq_qminout     = args.fastq_qminout,
            fastq_qmaxout     = args.fastq_qmaxout,
            fastq_minlen      = args.fastq_minlen,
            fastq_maxlen      = args.fastq_maxlen,
            fastq_maxns       = args.fastq_maxns,
            fastq_maxee       = args.fastq_maxee,
            allow_stagger     = args.allow_stagger,
        )
    except (FileNotFoundError, ValueError) as e:
        sys.exit(str(e))

    # 打印统计摘要
    total      = result["total"]
    merged_n   = result["merged"]
    not_merged = result["not_merged"]
    rate       = result["merge_rate"] * 100

    print(f"\n{'─'*45}")
    print(f"  总读段对数  : {total:>10}")
    print(f"  成功合并    : {merged_n:>10}  ({rate:.1f}%)")
    print(f"  未合并      : {not_merged:>10}  ({100-rate:.1f}%)")

    failed = result["failed"]
    if not_merged > 0:
        print(f"\n  未合并原因明细：")
        labels = {
            "minlen":       "读段过短（截断后）",
            "maxlen":       "读段过长",
            "maxns":        "N 碱基过多",
            "minovlen":     "重叠区过短",
            "maxdiffs":     "错配数过多",
            "maxdiffpct":   "错配比例过高",
            "staggered":    "Staggered 读段对",
            "repeat":       "多重比对（重复序列）",
            "minscore":     "比对得分过低",
            "nokmers":      "无 k-mer 命中",
            "minmergelen":  "合并序列过短",
            "maxmergelen":  "合并序列过长",
            "maxee":        "期望错误数过高",
            "undefined":    "未知原因",
        }
        for key, label in labels.items():
            count = failed.get(key, 0)
            if count > 0:
                print(f"    {label:<22}: {count:>8}")
    print(f"{'─'*45}\n")
    print(f"输出文件：{args.output}")


if __name__ == "__main__":
    main()
