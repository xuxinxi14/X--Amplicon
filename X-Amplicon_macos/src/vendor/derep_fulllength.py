"""
derep_fulllength.py
全长 FASTA 去冗余工具。

这个文件是对 vsearch `--derep_fulllength` 核心行为的纯 Python 重写版本。
目标不是做一个“差不多能用”的简化版，而是尽量在下面这些关键点上和
vsearch 保持一致：

1. 全长精确去冗余
2. 大小写不敏感比较，且标准化时把 U 视为 T
3. 丰度统计（size 计数）
4. 按 `丰度降序 -> 标题升序 -> 首次出现顺序` 排序输出
5. `--sizeout`、`--sizein`、`--minuniquesize`、`--relabel` 等参数行为
6. Windows 环境下按 CRLF 写 FASTA

依赖：
- Python 标准库
- pydantic >= 2.0

当前实现的能力：
- 输入 FASTA，支持普通文本和 gzip 压缩文件
- 支持标题截断规则，默认在第一个空格处截断
- 支持读取输入标题中的 `;size=N`
- 支持输出 `;size=N`
- 支持 `--relabel PREFIX` 形式的重标记
- 支持结构化统计结果返回

作为 Agent Tool 调用：
    from derep_fulllength import run

    result = run(
        {
            "derep_fulllength": "temp/filtered.fa",
            "output": "temp/unique_python.fa",
            "sizeout": True,
            "minuniquesize": 10,
            "relabel": "Uni_",
            "fasta_width": 80,
        }
    )

    print(result.total_kept)

命令行调用：
    python derep_fulllength.py ^
        --derep_fulllength temp/filtered.fa ^
        --output temp/unique_python.fa ^
        --sizeout ^
        --minuniquesize 10 ^
        --relabel Uni_ ^
        --fasta_width 80

16S 流程里常见的最简用法：
    python derep_fulllength.py ^
        --derep_fulllength temp/filtered.fa ^
        --output temp/uniques.fa ^
        --sizeout ^
        --minuniquesize 10 ^
        --relabel Uni_

输入字段说明：
- `input` / `derep_fulllength`：输入 FASTA 文件路径，两个字段二选一
- `fastaout` / `output`：输出 FASTA 文件路径，两个字段二选一
- `sizeout`：输出标题里是否追加 `;size=N`
- `sizein`：是否读取输入标题中的 `;size=N` 作为输入丰度
- `minuniquesize`：最小保留丰度，小于这个值的 unique 不输出
- `minlen`：最短序列长度，小于该值的输入序列直接丢弃
- `maxlen`：最长序列长度，默认 `-1` 表示不限制
- `relabel`：输出标题改成 `前缀 + 序号`，例如 `Uni_1`
- `relabel_keep`：重标记后是否把原标题保留在后面
- `notrunclabels`：是否不在第一个空格处截断标题
- `fasta_width`：输出序列每行宽度，`0` 表示单行，`80` 更接近 vsearch 默认输出

返回结果字段说明：
- `success`：是否成功执行
- `error`：失败时的错误信息
- `warnings`：警告信息列表，例如剥离了非标准字符
- `total_input`：输入记录总数
- `total_unique`：长度过滤后，去冗余得到的 unique 总数
- `total_kept`：应用 `minuniquesize` 后最终保留的 unique 数
- `discarded_low_abundance`：因丰度不足被过滤的 unique 数
- `discarded_too_short`：因序列太短被丢弃的输入记录数
- `discarded_too_long`：因序列太长被丢弃的输入记录数

几个容易混淆的点：
- `total_input` 是输入序列条数，不是输入文件字节数
- `discarded_too_short` 和 `discarded_too_long` 发生在“去重前”
- `discarded_low_abundance` 发生在“去重后”
- 如果想和你现有 `uniques.fa` 对拍一致，通常要显式传：
  `--sizeout --minuniquesize 10 --relabel Uni_ --fasta_width 80`
"""

from __future__ import annotations

import argparse
import gzip
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Iterator, Optional, Sequence

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


# 这里保留源码里的关键默认值，方便后续需要“严格按源码默认值”时参考。
VSEARCH_DEFAULT_MINSEQLENGTH = 32
VSEARCH_DEFAULT_MAXSEQLENGTH = 50000
VSEARCH_DEFAULT_FASTA_WIDTH = 80

# 任务书明确要求 Windows 下按 CRLF 输出。
CRLF = b"\r\n"

# FASTA 序列里被 vsearch 视为合法并保留的字符。
ACCEPTED_SEQUENCE_BYTES = set(b"ABCDGHKMNRSTUVWYabcdghkmnrstuvwy")


class RichHelpFormatter(
    argparse.ArgumentDefaultsHelpFormatter,
    argparse.RawTextHelpFormatter,
):
    """命令行帮助格式。

    这个格式类同时保留两件事：
    1. 自动显示默认值
    2. 保留多行示例的换行
    """


class DerepError(Exception):
    """内部使用的可控异常，统一转成结构化返回值。"""


class DerepFullLengthInput(BaseModel):
    """
    Agent 调用输入。

    说明：
    1. `input` / `derep_fulllength` 二选一，后者是 vsearch 风格别名。
    2. `fastaout` / `output` 二选一，后者是 vsearch 风格别名。
    3. `fasta_width` 默认按任务书使用 0，表示序列单行输出。
       如果你后面要严格模拟 vsearch 源码默认换行宽度，可显式传 80。
    """

    model_config = ConfigDict(extra="forbid")

    input: Optional[str] = Field(default=None, description="输入 FASTA 文件路径")
    derep_fulllength: Optional[str] = Field(
        default=None,
        description="vsearch 风格输入参数别名",
    )
    fastaout: Optional[str] = Field(default=None, description="输出去冗余 FASTA 文件路径")
    output: Optional[str] = Field(
        default=None,
        description="vsearch 风格输出参数别名",
    )
    sizeout: bool = Field(default=False, description="是否输出 ;size=N")
    sizein: bool = Field(
        default=False,
        description="是否读取输入标题中的 ;size=N 作为输入丰度",
    )
    minuniquesize: int = Field(default=1, description="最小保留丰度")
    minlen: int = Field(default=1, description="最短序列长度")
    maxlen: int = Field(default=-1, description="最长序列长度，-1 表示不限制")
    relabel: Optional[str] = Field(default=None, description="重标记前缀，例如 Uni_")
    relabel_keep: bool = Field(
        default=False,
        description="重标记后是否保留原始标题",
    )
    notrunclabels: bool = Field(
        default=False,
        description="是否不在第一个空格处截断标题",
    )
    fasta_width: int = Field(
        default=0,
        description="FASTA 序列每行宽度，0 表示单行输出",
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_alias_fields(cls, raw_data: object) -> object:
        """把 vsearch 风格别名统一折叠到主字段，减少后续分支。"""
        if not isinstance(raw_data, dict):
            return raw_data

        data = dict(raw_data)

        if data.get("input") is None and data.get("derep_fulllength") is not None:
            data["input"] = data["derep_fulllength"]

        if data.get("fastaout") is None and data.get("output") is not None:
            data["fastaout"] = data["output"]

        return data

    @model_validator(mode="after")
    def validate_values(self) -> "DerepFullLengthInput":
        """这里集中做参数合法性检查，避免主流程里散落判断。"""
        if not self.input:
            raise ValueError("缺少输入文件参数：请提供 input 或 derep_fulllength")

        if not self.fastaout:
            raise ValueError("缺少输出文件参数：请提供 fastaout 或 output")

        if self.minuniquesize < 1:
            raise ValueError("minuniquesize 不能小于 1")

        if self.minlen < 0:
            raise ValueError("minlen 不能为负数")

        if self.maxlen != -1 and self.maxlen < 1:
            raise ValueError("maxlen 必须为 -1 或大于等于 1")

        if self.maxlen != -1 and self.maxlen < self.minlen:
            raise ValueError("maxlen 不能小于 minlen")

        if self.fasta_width < 0:
            raise ValueError("fasta_width 不能为负数")

        return self


class DerepFullLengthOutput(BaseModel):
    """结构化输出，所有错误都通过这个模型返回。"""

    model_config = ConfigDict(extra="forbid")

    success: bool
    error: Optional[str] = None
    input: Optional[str] = None
    fastaout: Optional[str] = None
    warnings: list[str] = Field(default_factory=list)
    total_input: int = 0
    total_unique: int = 0
    total_kept: int = 0
    discarded_low_abundance: int = 0
    discarded_too_short: int = 0
    discarded_too_long: int = 0


@dataclass(slots=True)
class FastaRecord:
    """单条 FASTA 记录。"""

    header: bytes
    sequence: bytes


@dataclass(slots=True)
class ClusterRecord:
    """
    一个 unique cluster。

    注意：
    1. `header` 和 `sequence` 都保存“第一次出现”的原始值。
    2. 去重键另算，不直接覆盖原始序列。
    """

    header: bytes
    sequence: bytes
    size: int
    seqno_first: int


def _error_output(
    *,
    message: str,
    params: Optional[DerepFullLengthInput] = None,
    warnings: Optional[list[str]] = None,
    total_input: int = 0,
    total_unique: int = 0,
    total_kept: int = 0,
    discarded_low_abundance: int = 0,
    discarded_too_short: int = 0,
    discarded_too_long: int = 0,
) -> DerepFullLengthOutput:
    """统一生成失败结果，避免每个分支重复写样板代码。"""
    return DerepFullLengthOutput(
        success=False,
        error=message,
        input=params.input if params else None,
        fastaout=params.fastaout if params else None,
        warnings=warnings or [],
        total_input=total_input,
        total_unique=total_unique,
        total_kept=total_kept,
        discarded_low_abundance=discarded_low_abundance,
        discarded_too_short=discarded_too_short,
        discarded_too_long=discarded_too_long,
    )


def _open_input_handle(path: str) -> BinaryIO:
    """按文件魔数判断是否 gzip 输入。"""
    with open(path, "rb") as handle:
        magic = handle.read(2)

    if magic == b"\x1f\x8b":
        return gzip.open(path, "rb")

    return open(path, "rb")


def _trim_header(raw_header_line: bytes, truncate_at_space: bool, line_number: int) -> bytes:
    """
    复刻 fastx_filter_header 的核心行为。

    默认会在第一个空格或 tab 处截断标题；
    打开 notrunclabels 后，只去掉行结束符，不做空格截断。
    """
    if truncate_at_space:
        stop_bytes = {0, 9, 10, 13, 32}
    else:
        stop_bytes = {0, 10, 13}

    end = len(raw_header_line)
    for index, current_byte in enumerate(raw_header_line):
        if current_byte in stop_bytes:
            end = index
            break

    header = raw_header_line[:end]

    for current_byte in header:
        if current_byte == 127 or (0 < current_byte < 32 and current_byte != 9):
            raise DerepError(
                f"FASTA 标题包含非法控制字符，行号 {line_number}"
            )

    return header


def _filter_sequence_line(
    raw_sequence_line: bytes,
    line_number: int,
    stripped_counter: Counter[int],
) -> bytes:
    """
    复刻 fasta_filter_sequence 的核心行为。

    规则：
    1. 合法核酸字符原样保留，不改大小写。
    2. 空白字符去掉。
    3. '.' 和 '-' 直接报错。
    4. 其他可打印字符按 vsearch 思路视为“剥离并警告”。
    """
    kept = bytearray()

    for current_byte in raw_sequence_line:
        if current_byte in ACCEPTED_SEQUENCE_BYTES:
            kept.append(current_byte)
            continue

        if current_byte in (9, 10, 11, 12, 13):
            continue

        if current_byte in (45, 46):
            current_char = chr(current_byte)
            raise DerepError(
                f"FASTA 序列第 {line_number} 行含非法字符 '{current_char}'"
            )

        if current_byte < 32 or current_byte == 127:
            raise DerepError(
                f"FASTA 序列第 {line_number} 行含非法不可打印字符 {current_byte}"
            )

        stripped_counter[current_byte] += 1

    return bytes(kept)


def _iter_fasta_records(
    path: str,
    *,
    truncate_at_space: bool,
    stripped_counter: Counter[int],
) -> Iterator[FastaRecord]:
    """
    顺序读取 FASTA。

    这里用生成器逐条产出记录，避免先把整份文件全部读进内存。
    """
    current_header: Optional[bytes] = None
    current_sequence = bytearray()

    with _open_input_handle(path) as handle:
        line_number = 0

        for raw_line in handle:
            line_number += 1

            if raw_line.startswith(b">"):
                if not raw_line.endswith(b"\n"):
                    raise DerepError("Invalid FASTA - header must be terminated with newline")

                if current_header is not None:
                    yield FastaRecord(
                        header=current_header,
                        sequence=bytes(current_sequence),
                    )

                current_header = _trim_header(
                    raw_line[1:],
                    truncate_at_space=truncate_at_space,
                    line_number=line_number,
                )
                current_sequence = bytearray()
                continue

            if current_header is None:
                raise DerepError("Invalid FASTA - header must start with > character")

            current_sequence.extend(
                _filter_sequence_line(
                    raw_line,
                    line_number=line_number,
                    stripped_counter=stripped_counter,
                )
            )

        if current_header is not None:
            yield FastaRecord(
                header=current_header,
                sequence=bytes(current_sequence),
            )

def _append_stripped_warning(stripped_counter: Counter[int], warnings: list[str]) -> None:
    """把序列字符剥离统计整理成一条结构化警告。"""
    if not stripped_counter:
        return

    pieces: list[str] = []
    total_stripped = 0

    for byte_value in sorted(stripped_counter):
        count = stripped_counter[byte_value]
        total_stripped += count
        pieces.append(f"{chr(byte_value)!r}({count})")

    warnings.append(
        f"检测到并剥离 {total_stripped} 个非标准字符：{', '.join(pieces)}"
    )


def _normalize_sequence(sequence: bytes) -> bytes:
    """复刻 string_normalize：转大写，再把 U/u 变成 T。"""
    return sequence.upper().replace(b"U", b"T")


def _find_header_attribute(
    header: bytes,
    attribute: bytes,
    allow_decimal: bool = False,
) -> Optional[tuple[int, int]]:
    """
    复刻 header_find_attribute。

    返回值是半开区间 [start, end)：
    1. start 指向属性名开头，例如 size= 的 s。
    2. end 指向最后一个数字后面的下一个位置。
    """
    if not header or not attribute:
        return None

    if allow_decimal:
        digit_bytes = set(b"0123456789.")
    else:
        digit_bytes = set(b"0123456789")

    offset = 0
    header_length = len(header)
    attribute_length = len(attribute)

    while offset < header_length - attribute_length:
        start = header.find(attribute, offset)
        if start < 0:
            return None

        if start > 0 and header[start - 1] != 59:
            offset = start + attribute_length + 1
            continue

        digit_count = 0
        scan_index = start + attribute_length
        while scan_index < header_length and header[scan_index] in digit_bytes:
            digit_count += 1
            scan_index += 1

        if digit_count == 0:
            offset = start + attribute_length + 1
            continue

        if scan_index < header_length and header[scan_index] != 59:
            offset = start + attribute_length + digit_count + 2
            continue

        return start, start + attribute_length + digit_count

    return None


def _header_get_size(header: bytes) -> int:
    """读取标题里的 ;size=N。不存在时返回 0。"""
    found = _find_header_attribute(header, b"size=", allow_decimal=False)
    if found is None:
        return 0

    start, end = found
    value_bytes = header[start + len(b"size="):end]
    abundance = int(value_bytes)

    if abundance == 0:
        raise DerepError("Invalid (zero) abundance annotation in FASTA file header")

    return abundance


def _header_strip_attributes(
    header: bytes,
    *,
    strip_size: bool,
    strip_ee: bool,
    strip_length: bool,
) -> bytes:
    """
    复刻 header_fprint_strip 的核心逻辑。

    这里只处理 derep_fulllength 需要的几个属性。
    """
    attributes: list[tuple[int, int]] = []

    if strip_size:
        found = _find_header_attribute(header, b"size=", allow_decimal=False)
        if found is not None:
            attributes.append(found)

    if strip_ee:
        found = _find_header_attribute(header, b"ee=", allow_decimal=False)
        if found is not None:
            attributes.append(found)

    if strip_length:
        found = _find_header_attribute(header, b"length=", allow_decimal=False)
        if found is not None:
            attributes.append(found)

    if not attributes:
        return header

    attributes.sort(key=lambda item: item[0])

    pieces: list[bytes] = []
    previous_end = 0

    for start, end in attributes:
        if start > previous_end + 1:
            pieces.append(header[previous_end:start - 1])
        previous_end = end

    if len(header) > previous_end + 1:
        pieces.append(header[previous_end:])

    return b"".join(pieces)


def _format_output_header(
    cluster: ClusterRecord,
    *,
    params: DerepFullLengthInput,
    ordinal: int,
) -> bytes:
    """
    按 fasta_print_general 的 derep 路径拼标题。

    这里只实现 derep_fulllength 真正会走到的分支：
    1. 不支持 md5/sha1/self relabel，因为任务书没要求。
    2. 但严格保留 relabel、relabel_keep、sizeout 的顺序。
    """
    parts: list[bytes] = [b">"]

    relabel_is_active = params.relabel is not None and ordinal > 0

    if relabel_is_active:
        parts.append(params.relabel.encode("ascii"))
        parts.append(str(ordinal).encode("ascii"))
    else:
        stripped_header = _header_strip_attributes(
            cluster.header,
            strip_size=params.sizeout and cluster.size > 0,
            strip_ee=False,
            strip_length=False,
        )
        parts.append(stripped_header)

    if params.sizeout and cluster.size > 0:
        parts.append(b";size=")
        parts.append(str(cluster.size).encode("ascii"))

    if params.relabel_keep and relabel_is_active:
        parts.append(b" ")
        parts.append(cluster.header)

    parts.append(CRLF)
    return b"".join(parts)


def _format_output_sequence(sequence: bytes, fasta_width: int) -> bytes:
    """按指定宽度写 FASTA 序列，0 表示单行输出。"""
    if fasta_width < 1:
        return sequence + CRLF

    pieces: list[bytes] = []
    index = 0
    sequence_length = len(sequence)

    while index < sequence_length:
        pieces.append(sequence[index:index + fasta_width])
        pieces.append(CRLF)
        index += fasta_width

    return b"".join(pieces)


def _write_fasta_output(
    output_path: str,
    sorted_clusters: list[ClusterRecord],
    params: DerepFullLengthInput,
) -> int:
    """
    写出去冗余结果。

    返回值是实际写出的 unique 数量，和 vsearch 的 relabel_count 对齐。
    """
    relabel_count = 0

    if output_path == "-":
        output_handle = sys.stdout.buffer
        should_close = False
    else:
        output_handle = open(output_path, "wb")
        should_close = True

    try:
        for cluster in sorted_clusters:
            if cluster.size < params.minuniquesize:
                continue

            relabel_count += 1
            output_handle.write(
                _format_output_header(
                    cluster,
                    params=params,
                    ordinal=relabel_count,
                )
            )
            output_handle.write(
                _format_output_sequence(
                    cluster.sequence,
                    fasta_width=params.fasta_width,
                )
            )
    finally:
        if should_close:
            output_handle.close()

    return relabel_count


def _run_derep(params: DerepFullLengthInput) -> DerepFullLengthOutput:
    """真正的业务主流程。"""
    input_path = Path(params.input)
    if not input_path.exists():
        raise DerepError(f"输入文件不存在：{params.input}")

    warnings: list[str] = []

    stripped_counter: Counter[int] = Counter()
    total_input = 0
    discarded_too_short = 0
    discarded_too_long = 0

    clusters: list[ClusterRecord] = []
    cluster_index_by_sequence: dict[bytes, int] = {}

    for seqno, record in enumerate(
        _iter_fasta_records(
            params.input,
            truncate_at_space=not params.notrunclabels,
            stripped_counter=stripped_counter,
        )
    ):
        total_input += 1
        sequence_length = len(record.sequence)

        if sequence_length < params.minlen:
            discarded_too_short += 1
            continue

        if params.maxlen != -1 and sequence_length > params.maxlen:
            discarded_too_long += 1
            continue

        normalized_sequence = _normalize_sequence(record.sequence)

        if params.sizein:
            abundance = _header_get_size(record.header)
            if abundance <= 0:
                abundance = 1
        else:
            abundance = 1

        existing_index = cluster_index_by_sequence.get(normalized_sequence)
        if existing_index is not None:
            clusters[existing_index].size += abundance
            continue

        cluster_index_by_sequence[normalized_sequence] = len(clusters)
        clusters.append(
            ClusterRecord(
                header=record.header,
                sequence=record.sequence,
                size=abundance,
                seqno_first=seqno,
            )
        )

    _append_stripped_warning(stripped_counter, warnings)

    sorted_clusters = sorted(
        clusters,
        key=lambda cluster: (-cluster.size, cluster.header, cluster.seqno_first),
    )

    total_unique = len(sorted_clusters)
    total_kept = sum(1 for cluster in sorted_clusters if cluster.size >= params.minuniquesize)
    discarded_low_abundance = total_unique - total_kept

    _write_fasta_output(params.fastaout, sorted_clusters, params)

    return DerepFullLengthOutput(
        success=True,
        error=None,
        input=params.input,
        fastaout=params.fastaout,
        warnings=warnings,
        total_input=total_input,
        total_unique=total_unique,
        total_kept=total_kept,
        discarded_low_abundance=discarded_low_abundance,
        discarded_too_short=discarded_too_short,
        discarded_too_long=discarded_too_long,
    )


def run(data: DerepFullLengthInput | dict) -> DerepFullLengthOutput:
    """
    Agent 入口。

    要求：
    1. 不 print。
    2. 不 sys.exit。
    3. 所有错误都返回结构化结果。
    """
    try:
        params = data if isinstance(data, DerepFullLengthInput) else DerepFullLengthInput.model_validate(data)
    except ValidationError as exc:
        return _error_output(message=str(exc))

    try:
        return _run_derep(params)
    except DerepError as exc:
        return _error_output(message=str(exc), params=params)
    except OSError as exc:
        return _error_output(message=f"文件读写失败：{exc}", params=params)
    except Exception as exc:  # pragma: no cover
        return _error_output(message=f"未预期错误：{exc}", params=params)


def _build_arg_parser() -> argparse.ArgumentParser:
    """命令行入口，尽量兼容 vsearch 常用参数名。"""
    examples = (
        "示例：\n"
        "  1. 最常见的 16S 去冗余\n"
        "     python derep_fulllength.py ^\n"
        "         --derep_fulllength temp/filtered.fa ^\n"
        "         --output temp/uniques.fa ^\n"
        "         --sizeout ^\n"
        "         --minuniquesize 10 ^\n"
        "         --relabel Uni_ ^\n"
        "         --fasta_width 80\n"
        "\n"
        "  2. 如果想把序列强制写成单行\n"
        "     python derep_fulllength.py ^\n"
        "         --derep_fulllength input.fa ^\n"
        "         --output uniques.fa ^\n"
        "         --sizeout ^\n"
        "         --fasta_width 0\n"
        "\n"
        "  3. 如果输入标题本身已经带有 ;size= 注释\n"
        "     python derep_fulllength.py ^\n"
        "         --derep_fulllength input.fa ^\n"
        "         --output uniques.fa ^\n"
        "         --sizein ^\n"
        "         --sizeout\n"
    )

    parser = argparse.ArgumentParser(
        description=(
            "纯 Python 版 derep_fulllength。\n"
            "功能：对 FASTA 做全长精确去冗余，并按 vsearch 风格输出 unique FASTA。"
        ),
        epilog=examples,
        formatter_class=RichHelpFormatter,
    )
    parser.add_argument(
        "--derep_fulllength",
        dest="derep_fulllength",
        help="输入 FASTA 文件，vsearch 风格主参数",
    )
    parser.add_argument(
        "--input",
        dest="input",
        help="输入 FASTA 文件，Agent 风格别名",
    )
    parser.add_argument(
        "--fastaout",
        dest="fastaout",
        help="输出 FASTA 文件，Agent 风格字段名",
    )
    parser.add_argument(
        "--output",
        dest="output",
        help="输出 FASTA 文件，vsearch 风格字段名",
    )
    parser.add_argument(
        "--sizeout",
        action="store_true",
        help="在输出标题后追加 ;size=N",
    )
    parser.add_argument(
        "--sizein",
        action="store_true",
        help="读取输入标题中的 ;size=N 作为输入丰度",
    )
    parser.add_argument(
        "--minuniquesize",
        type=int,
        default=1,
        help="最小保留丰度，小于该值的 unique 不输出",
    )
    parser.add_argument(
        "--minlen",
        type=int,
        default=1,
        help="最短序列长度，小于该值的输入序列直接丢弃",
    )
    parser.add_argument(
        "--minseqlength",
        dest="minlen",
        type=int,
        help="vsearch 风格别名，等价于 --minlen",
    )
    parser.add_argument(
        "--maxlen",
        type=int,
        default=-1,
        help="最长序列长度，-1 表示不限制",
    )
    parser.add_argument(
        "--maxseqlength",
        dest="maxlen",
        type=int,
        help="vsearch 风格别名，等价于 --maxlen",
    )
    parser.add_argument(
        "--relabel",
        type=str,
        default=None,
        help="把输出标题改成 前缀+序号，例如 Uni_1、Uni_2",
    )
    parser.add_argument(
        "--relabel_keep",
        action="store_true",
        help="重标记后保留原标题，格式类似 新标题 旧标题",
    )
    parser.add_argument(
        "--notrunclabels",
        action="store_true",
        help="不在第一个空格处截断标题；默认会截断到第一个空格前",
    )
    parser.add_argument(
        "--fasta_width",
        type=int,
        default=0,
        help="输出序列每行宽度；0 表示单行，80 更接近 vsearch 默认输出样式",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """
    命令行入口。

    这里允许向终端输出，因为这是 CLI，而不是 Agent 函数调用入口。
    """
    parser = _build_arg_parser()
    namespace = parser.parse_args(argv)
    result = run(vars(namespace))

    if not result.success:
        print(result.error, file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
