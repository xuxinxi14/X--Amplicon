"""fastx_filter.py
单端 FASTA/FASTQ 过滤工具。

这个文件是对 vsearch `fastx_filter` 核心子集的纯 Python 重写。
代码专门按当前 16S 流程需求保留最关键的部分，
目标是让没有 C/C++ 基础的人也能直接读懂和调用。

依赖：
- Python 3.10+
- pydantic >= 2.0

当前已经实现的功能：
- 单端 FASTQ 输入
- 单端 FASTA 输入
- 自动识别 gzip 压缩输入
- 自动写出普通 FASTA 或 gzip 压缩 FASTA
- `--fastq_stripleft` 左端固定剪切
- `--fastq_stripright` 右端固定剪切
- `--fastq_maxee_rate` 按平均期望错误率过滤
- `--fastq_maxns` 按 N 碱基数量过滤
- `--fastq_minlen` / `--minlen` 按最短长度过滤
- 输出结构化统计结果

参数规则：
- `fastq_stripleft` 默认是 0，表示左端不剪切
- `fastq_stripright` 默认是 0，表示右端不剪切
- `fastq_maxee_rate` 默认是 -1，表示禁用这个过滤条件
- `fastq_maxns` 默认是 -1，表示禁用这个过滤条件
- `minlen` 默认是 1，表示长度至少保留 1 bp
- 这里严格保留 vsearch 风格：`-1` 表示“禁用过滤”，不能随意改成 0

作为 Agent Tool 调用：
    from fastx_filter import FastxFilterInput, run

    result = run(
        FastxFilterInput(
            fastx_filter="temp/all.fq",
            fastaout="temp/filtered_python.fa",
            fastq_stripleft=29,
            fastq_stripright=18,
            fastq_maxee_rate=0.01,
            fastq_maxns=-1,
            minlen=1,
        )
    )

    if result.success:
        print(result.stats.kept_reads)
    else:
        print(result.error.message)

命令行调用：
    python fastx_filter.py ^
        --fastx_filter temp/all.fq ^
        --fastq_stripleft 29 ^
        --fastq_stripright 18 ^
        --fastq_maxee_rate 0.01 ^
        --fastaout temp/filtered_python.fa

最常见的 16S 用法：
    python fastx_filter.py ^
        --fastx_filter temp/all.fq ^
        --fastq_stripleft 29 ^
        --fastq_stripright 18 ^
        --fastq_maxee_rate 0.01 ^
        --fastaout temp/filtered_python.fa

返回统计字段说明：
- `total_reads`：输入序列总数
- `kept_reads`：通过过滤并写出的序列数
- `discarded_reads`：被过滤掉的序列数
- `truncated_reads`：发生过剪切的保留序列数
- `filtered_rate`：保留比例，单位是百分比
- `failed_too_short`：因为长度不足被过滤的数量
- `failed_maxee_rate`：因为平均期望错误率超标被过滤的数量
- `failed_maxns`：因为 N 碱基数量超标被过滤的数量

说明：
- 这个版本当前只覆盖本任务要求的核心子集，不包含 vsearch 全部参数
- FASTA 输出默认按 80 列折行
- Windows 下写出与当前参考结果一致的 CRLF 换行
"""

from __future__ import annotations

import argparse
import gzip
import math
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO
from typing import Optional

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic import field_validator


# vsearch 的 FASTA 默认折行宽度是 80。
FASTA_WIDTH = 80

# 当前任务运行环境是 Windows，vsearch 参考文件使用 CRLF。
OUTPUT_NEWLINE = b"\r\n"

# vsearch 默认使用 Phred33。
FASTQ_ASCII_OFFSET = 33

# vsearch 默认允许的 FASTQ 质量值范围是 0 到 41。
FASTQ_QMIN = 0
FASTQ_QMAX = 41

# vsearch FASTQ 序列允许的 IUPAC 字符。
VALID_FASTQ_SEQUENCE_BYTES = {
    ord("A"),
    ord("B"),
    ord("C"),
    ord("D"),
    ord("G"),
    ord("H"),
    ord("K"),
    ord("M"),
    ord("N"),
    ord("R"),
    ord("S"),
    ord("T"),
    ord("U"),
    ord("V"),
    ord("W"),
    ord("Y"),
    ord("a"),
    ord("b"),
    ord("c"),
    ord("d"),
    ord("g"),
    ord("h"),
    ord("k"),
    ord("m"),
    ord("n"),
    ord("r"),
    ord("s"),
    ord("t"),
    ord("u"),
    ord("v"),
    ord("w"),
    ord("y"),
}


class ErrorInfo(BaseModel):
    """结构化错误信息。"""

    code: str
    message: str
    line_number: Optional[int] = None


class FastxFilterStats(BaseModel):
    """结构化统计信息。"""

    total_reads: int = 0
    kept_reads: int = 0
    discarded_reads: int = 0
    truncated_reads: int = 0
    filtered_rate: float = 0.0
    failed_too_short: int = 0
    failed_maxee_rate: int = 0
    failed_maxns: int = 0
    output_format: str = "FASTA"


class FastxFilterInput(BaseModel):
    """Agent 调用时使用的结构化输入。"""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    # 为了兼容 vsearch 风格，这里给输入文件路径加了别名 fastx_filter。
    input_path: str = Field(alias="fastx_filter")
    fastaout: Optional[str] = None
    fastq_stripleft: int = 0
    fastq_stripright: int = 0
    fastq_maxee_rate: float = -1.0
    fastq_maxns: int = -1
    minlen: int = 1

    @field_validator("input_path")
    @classmethod
    def validate_input_path(cls, value: str) -> str:
        """输入路径不能为空。"""
        if not value:
            raise ValueError("input_path cannot be empty")
        return value

    @field_validator("fastq_stripleft", "fastq_stripright")
    @classmethod
    def validate_strip_length(cls, value: int) -> int:
        """固定剪切长度必须是非负整数。"""
        if value < 0:
            raise ValueError("strip length cannot be negative")
        return value

    @field_validator("fastq_maxns")
    @classmethod
    def validate_fastq_maxns(cls, value: int) -> int:
        """fastq_maxns 允许 -1 表示禁用，其它值不能小于 0。"""
        if value < -1:
            raise ValueError("fastq_maxns must be -1 or a non-negative integer")
        return value

    @field_validator("minlen")
    @classmethod
    def validate_minlen(cls, value: int) -> int:
        """minlen 允许 -1 表示禁用。"""
        if value < -1:
            raise ValueError("minlen must be -1 or greater")
        return value

    @field_validator("fastq_maxee_rate")
    @classmethod
    def validate_fastq_maxee_rate(cls, value: float) -> float:
        """fastq_maxee_rate 允许 -1 表示禁用。"""
        if value < 0 and value != -1:
            raise ValueError("fastq_maxee_rate must be -1 or a non-negative number")
        return value


class FastxFilterOutput(BaseModel):
    """run() 和 main() 统一返回的结构化结果。"""

    success: bool
    input_format: Optional[str] = None
    output_path: Optional[str] = None
    stats: FastxFilterStats = Field(default_factory=FastxFilterStats)
    warnings: list[str] = Field(default_factory=list)
    error: Optional[ErrorInfo] = None


class StructuredFastxError(Exception):
    """内部异常，最终会被转换成结构化返回值。"""

    def __init__(
        self,
        code: str,
        message: str,
        line_number: Optional[int] = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.line_number = line_number


class ArgumentParserError(Exception):
    """argparse 错误，避免直接 sys.exit。"""


class SafeArgumentParser(argparse.ArgumentParser):
    """不会直接退出进程的 argparse。"""

    def error(self, message: str) -> None:
        raise ArgumentParserError(message)

    def exit(self, status: int = 0, message: Optional[str] = None) -> None:
        if message:
            raise ArgumentParserError(message)
        raise ArgumentParserError(f"argument parser exit with status {status}")


@dataclass
class ParsedRecord:
    """一条已经解析好的序列记录。"""

    header: str
    sequence: str
    quality: Optional[str]
    line_number: int


@dataclass
class AnalysisResult:
    """一条记录经过 fastx_filter 后的分析结果。"""

    discarded: bool
    truncated: bool
    start: int
    length: int
    expected_error: float
    failed_too_short: bool
    failed_maxee_rate: bool
    failed_maxns: bool


class BinaryLineReader:
    """简单的二进制按行读取器。

    这里保留原始字节，原因是：
    1. vsearch 按字节判断 gzip、FASTA、FASTQ。
    2. Windows 文本模式会改换行，二进制更安全。
    3. 头部里的非 ASCII 字节需要 1:1 保留。
    """

    def __init__(self, handle: BinaryIO) -> None:
        self.handle = handle
        self._buffered_line: Optional[tuple[bytes, int]] = None
        self.next_line_number = 1

    def readline(self) -> Optional[tuple[bytes, int]]:
        """读取一行，并返回这行的原始字节和起始行号。"""
        if self._buffered_line is not None:
            line = self._buffered_line
            self._buffered_line = None
            return line

        data = self.handle.readline()
        if data == b"":
            return None

        start_line = self.next_line_number
        if data.endswith(b"\n"):
            self.next_line_number += 1
        return data, start_line

    def pushback(self, line: bytes, line_number: int) -> None:
        """把一行放回缓冲区，供下一次读取。"""
        self._buffered_line = (line, line_number)


def _detect_gzip(path: Path) -> bool:
    """按魔数判断输入是否是 gzip。

    这和 vsearch 的思路一致，不依赖文件扩展名。
    """
    with path.open("rb") as handle:
        magic = handle.read(2)
    return magic == b"\x1f\x8b"


def _open_input_handle(path: str) -> BinaryIO:
    """按 vsearch 风格打开输入。

    gzip 输入按魔数自动识别。
    """
    input_path = Path(path)
    if not input_path.exists():
        raise StructuredFastxError(
            code="INPUT_NOT_FOUND",
            message=f"Unable to open file for reading ({path})",
        )

    if _detect_gzip(input_path):
        return gzip.open(input_path, "rb")
    return input_path.open("rb")


def _open_output_handle(path: str) -> BinaryIO:
    """打开输出文件。

    这里按文件后缀决定是否写 gzip。
    写出全部使用二进制模式，确保换行固定为 LF。
    """
    output_path = Path(path)
    if output_path.suffix.lower() == ".gz":
        return gzip.open(output_path, "wb")
    return output_path.open("wb")


def _to_output_model(
    *,
    success: bool,
    stats: FastxFilterStats,
    warnings: list[str],
    output_path: Optional[str] = None,
    input_format: Optional[str] = None,
    error: Optional[StructuredFastxError] = None,
) -> FastxFilterOutput:
    """把内部状态统一转换成结构化输出。"""
    error_info: Optional[ErrorInfo] = None
    if error is not None:
        error_info = ErrorInfo(
            code=error.code,
            message=error.message,
            line_number=error.line_number,
        )

    return FastxFilterOutput(
        success=success,
        input_format=input_format,
        output_path=output_path,
        stats=stats,
        warnings=warnings,
        error=error_info,
    )


def _normalize_header(raw_header: bytes, line_number: int, warnings: list[str]) -> str:
    """复刻 fastx_filter_header 的头部裁剪和合法性检查。

    filter.cc 调 fastx_next(..., false, ...)。
    也就是：
    - 不在空格处分断头部
    - 只在 NUL / CR / LF 处分断
    """
    end_index = len(raw_header)
    for stop_byte in (0, 13, 10):
        position = raw_header.find(bytes([stop_byte]))
        if position != -1 and position < end_index:
            end_index = position

    header_bytes = raw_header[:end_index]

    for symbol in header_bytes:
        is_illegal = symbol == 127 or (0 < symbol < 32 and symbol != 9)
        if is_illegal:
            raise StructuredFastxError(
                code="INVALID_HEADER",
                message=(
                    "Illegal character encountered in FASTA/FASTQ header.\n"
                    f"Unprintable ASCII character no {symbol} on line {line_number}."
                ),
                line_number=line_number,
            )
        if symbol > 127:
            warnings.append(
                "Non-ASCII character encountered in FASTA/FASTQ header.\n"
                f"Character no {symbol} (0x{symbol:02x}) on line {line_number}."
            )

    return header_bytes.decode("latin-1")


def _raise_fastq_sequence_error(symbol: int, line_number: int) -> None:
    """复刻 FASTQ 序列非法字符报错。"""
    if 32 <= symbol < 127:
        message = f"Invalid line {line_number} in FASTQ file: Illegal sequence character '{chr(symbol)}'"
    else:
        message = (
            f"Invalid line {line_number} in FASTQ file: "
            f"Illegal sequence character (unprintable, no {symbol})"
        )
    raise StructuredFastxError(
        code="INVALID_FASTQ_SEQUENCE",
        message=message,
        line_number=line_number,
    )


def _raise_fastq_quality_error(symbol: int, line_number: int) -> None:
    """复刻 FASTQ 质量字符非法报错。"""
    if 32 <= symbol < 127:
        message = f"Invalid line {line_number} in FASTQ file: Illegal quality character '{chr(symbol)}'"
    else:
        message = (
            f"Invalid line {line_number} in FASTQ file: "
            f"Illegal quality character (unprintable, no {symbol})"
        )
    raise StructuredFastxError(
        code="INVALID_FASTQ_QUALITY",
        message=message,
        line_number=line_number,
    )


def _filter_fastq_sequence_bytes(raw_line: bytes, line_number: int) -> str:
    """按 vsearch 的 FASTQ 序列规则过滤一行。

    规则非常直接：
    - IUPAC 字符保留
    - CR/LF 静默剥离
    - 其它字符一律报错
    """
    kept = bytearray()
    for symbol in raw_line:
        if symbol in VALID_FASTQ_SEQUENCE_BYTES:
            kept.append(symbol)
            continue
        if symbol in (10, 13):
            continue
        _raise_fastq_sequence_error(symbol, line_number)
    return kept.decode("latin-1")


def _filter_fastq_quality_bytes(raw_line: bytes, line_number: int) -> str:
    """按 vsearch 的 FASTQ 质量规则过滤一行。"""
    kept = bytearray()
    for symbol in raw_line:
        if 33 <= symbol <= 126:
            kept.append(symbol)
            continue
        if symbol in (10, 13):
            continue
        _raise_fastq_quality_error(symbol, line_number)
    return kept.decode("latin-1")


def _filter_fasta_sequence_line(
    raw_line: bytes,
    line_number: int,
    warnings: list[str],
    stripped_counts: dict[int, int],
) -> str:
    """按 vsearch 的 FASTA 序列规则过滤一行。

    这里和 FASTQ 不一样：
    - 合法 IUPAC 字符保留
    - 制表符、换页、回车、换行等空白会被静默移除
    - '.' 和 '-' 会直接报错
    - 其它可打印字符和非 ASCII 字符会被剥离，并在最终给警告
    """
    kept = bytearray()
    _ = warnings

    for symbol in raw_line:
        if symbol in VALID_FASTQ_SEQUENCE_BYTES:
            kept.append(symbol)
            continue

        if symbol == 10:
            continue

        if symbol in (9, 11, 12, 13):
            continue

        if symbol in (45, 46):
            raise StructuredFastxError(
                code="INVALID_FASTA_SEQUENCE",
                message=(
                    f"Illegal character '{chr(symbol)}' in sequence "
                    f"on line {line_number} of FASTA file"
                ),
                line_number=line_number,
            )

        if symbol == 127 or (symbol < 32):
            raise StructuredFastxError(
                code="INVALID_FASTA_SEQUENCE",
                message=(
                    f"Illegal unprintable ASCII character no {symbol} "
                    f"in sequence on line {line_number} of FASTA file"
                ),
                line_number=line_number,
            )

        stripped_counts[symbol] = stripped_counts.get(symbol, 0) + 1

    return kept.decode("latin-1")


def _quality_symbol_to_score(symbol: str) -> int:
    """复刻 filter.cc 里的 fastq_get_qual。"""
    quality_score = ord(symbol) - FASTQ_ASCII_OFFSET

    if quality_score < FASTQ_QMIN:
        raise StructuredFastxError(
            code="FASTQ_QUALITY_BELOW_QMIN",
            message=(
                "\n\nFatal error: FASTQ quality value "
                f"({quality_score}) below qmin ({FASTQ_QMIN})\n"
            ),
        )

    if quality_score > FASTQ_QMAX:
        raise StructuredFastxError(
            code="FASTQ_QUALITY_ABOVE_QMAX",
            message=(
                "\n\nFatal error: FASTQ quality value "
                f"({quality_score}) above qmax ({FASTQ_QMAX})\n"
                "By default, quality values range from 0 to 41.\n"
                f"To allow higher quality values, please use the option --fastq_qmax {quality_score}\n"
            ),
        )

    return quality_score


def _parse_fastq_record(reader: BinaryLineReader, warnings: list[str]) -> Optional[ParsedRecord]:
    """解析一条 FASTQ 记录。"""
    header_row = reader.readline()
    if header_row is None:
        return None

    header_line, header_line_number = header_row
    if not header_line.endswith(b"\n"):
        raise StructuredFastxError(
            code="INVALID_FASTQ_EOF",
            message=f"Invalid line {header_line_number} in FASTQ file: Unexpected end of file",
            line_number=header_line_number,
        )

    if not header_line.startswith(b"@"):
        raise StructuredFastxError(
            code="INVALID_FASTQ_HEADER",
            message="Invalid line "
            f"{header_line_number} in FASTQ file: Header line must start with '@' character",
            line_number=header_line_number,
        )

    raw_header = header_line[1:]

    sequence_parts: list[str] = []
    sequence_length = 0
    while True:
        row = reader.readline()
        if row is None:
            raise StructuredFastxError(
                code="INVALID_FASTQ_EOF",
                message=f"Invalid line {reader.next_line_number} in FASTQ file: Unexpected end of file",
                line_number=reader.next_line_number,
            )

        line_bytes, line_number = row
        if line_bytes.startswith(b"+"):
            plus_line = line_bytes
            break

        filtered_sequence = _filter_fastq_sequence_bytes(line_bytes, line_number)
        sequence_parts.append(filtered_sequence)
        sequence_length += len(filtered_sequence)

    if not plus_line.endswith(b"\n"):
        raise StructuredFastxError(
            code="INVALID_FASTQ_EOF",
            message=f"Invalid line {line_number} in FASTQ file: Unexpected end of file",
            line_number=line_number,
        )

    plus_payload = plus_line[1:]
    plus_invalid = False
    if len(raw_header) == len(plus_payload):
        if raw_header != plus_payload:
            plus_invalid = True
    else:
        if len(plus_payload) > 2:
            plus_invalid = True
        elif len(plus_payload) == 2 and plus_payload[0] != 13:
            plus_invalid = True

    if plus_invalid:
        raise StructuredFastxError(
            code="INVALID_FASTQ_PLUS_LINE",
            message=(
                f"Invalid line {line_number} in FASTQ file: "
                "'+' line must be empty or identical to header"
            ),
            line_number=line_number,
        )

    sequence = "".join(sequence_parts)

    quality_parts: list[str] = []
    quality_length = 0
    last_quality_line_number = line_number

    while True:
        row = reader.readline()
        if row is None:
            break

        line_bytes, line_number = row
        last_quality_line_number = line_number

        if line_bytes.startswith(b"@") and quality_length == sequence_length:
            reader.pushback(line_bytes, line_number)
            break

        filtered_quality = _filter_fastq_quality_bytes(line_bytes, line_number)
        quality_parts.append(filtered_quality)
        quality_length += len(filtered_quality)

        if quality_length > sequence_length:
            break

    quality = "".join(quality_parts)

    if len(sequence) != len(quality):
        raise StructuredFastxError(
            code="FASTQ_LENGTH_MISMATCH",
            message=(
                f"Invalid line {last_quality_line_number} in FASTQ file: "
                "Sequence and quality lines must be equally long"
            ),
            line_number=last_quality_line_number,
        )

    header = _normalize_header(raw_header, header_line_number, warnings)
    return ParsedRecord(
        header=header,
        sequence=sequence,
        quality=quality,
        line_number=header_line_number,
    )


def _parse_fasta_record(
    reader: BinaryLineReader,
    warnings: list[str],
    stripped_counts: dict[int, int],
) -> Optional[ParsedRecord]:
    """解析一条 FASTA 记录。"""
    header_row = reader.readline()
    if header_row is None:
        return None

    header_line, header_line_number = header_row
    if not header_line.endswith(b"\n"):
        raise StructuredFastxError(
            code="INVALID_FASTA_HEADER",
            message="Invalid FASTA - header must be terminated with newline",
            line_number=header_line_number,
        )

    if not header_line.startswith(b">"):
        found_symbol = header_line[0]
        raise StructuredFastxError(
            code="INVALID_FASTA_HEADER",
            message=(
                "Invalid FASTA - header must start with > character"
                f" (found 0x{found_symbol:02x})"
            ),
            line_number=header_line_number,
        )

    raw_header = header_line[1:]
    sequence_parts: list[str] = []

    while True:
        row = reader.readline()
        if row is None:
            break

        line_bytes, line_number = row
        if line_bytes.startswith(b">"):
            reader.pushback(line_bytes, line_number)
            break

        sequence_parts.append(
            _filter_fasta_sequence_line(
                raw_line=line_bytes,
                line_number=line_number,
                warnings=warnings,
                stripped_counts=stripped_counts,
            )
        )

    header = _normalize_header(raw_header, header_line_number, warnings)
    sequence = "".join(sequence_parts)

    return ParsedRecord(
        header=header,
        sequence=sequence,
        quality=None,
        line_number=header_line_number,
    )


def _count_ns(sequence: str) -> int:
    """统计 N/n 的数量。"""
    count = 0
    for symbol in sequence:
        if symbol == "N" or symbol == "n":
            count += 1
    return count


def _analyze_record(record: ParsedRecord, params: FastxFilterInput) -> AnalysisResult:
    """复刻 filter.cc 里的 analyse() 核心逻辑。

    当前任务要求的参数只有：
    - fastq_stripleft
    - fastq_stripright
    - fastq_maxee_rate
    - fastq_maxns
    - minlen
    """
    sequence_length = len(record.sequence)
    start = 0
    length = sequence_length
    expected_error = -1.0
    discarded = False

    # 对齐 vsearch：先剪左端。
    if params.fastq_stripleft < length:
        start += params.fastq_stripleft
        length -= params.fastq_stripleft
    else:
        start = length
        length = 0

    # 对齐 vsearch：再剪右端。
    if params.fastq_stripright < length:
        length -= params.fastq_stripright
    else:
        length = 0

    failed_maxee_rate = False
    if record.quality is not None:
        expected_error = 0.0
        quality_part = record.quality[start : start + length]
        for quality_symbol in quality_part:
            quality_score = _quality_symbol_to_score(quality_symbol)
            expected_error += math.pow(10.0, -quality_score / 10.0)

        if params.fastq_maxee_rate >= 0:
            if length > 0 and (expected_error / length) > params.fastq_maxee_rate:
                discarded = True
                failed_maxee_rate = True

    failed_too_short = False
    if params.minlen >= 0:
        if length < params.minlen:
            discarded = True
            failed_too_short = True

    failed_maxns = False
    if params.fastq_maxns >= 0:
        ncount = _count_ns(record.sequence[start : start + length])
        if ncount > params.fastq_maxns:
            discarded = True
            failed_maxns = True

    truncated = length < sequence_length

    return AnalysisResult(
        discarded=discarded,
        truncated=truncated,
        start=start,
        length=length,
        expected_error=expected_error,
        failed_too_short=failed_too_short,
        failed_maxee_rate=failed_maxee_rate,
        failed_maxns=failed_maxns,
    )


def _write_fasta_record(handle: BinaryIO, header: str, sequence: str) -> None:
    """按 vsearch 默认 FASTA 风格写一条记录。"""
    handle.write(b">")
    handle.write(header.encode("latin-1"))
    handle.write(OUTPUT_NEWLINE)

    if FASTA_WIDTH < 1:
        handle.write(sequence.encode("latin-1"))
        handle.write(OUTPUT_NEWLINE)
        return

    start = 0
    while start < len(sequence):
        end = start + FASTA_WIDTH
        handle.write(sequence[start:end].encode("latin-1"))
        handle.write(OUTPUT_NEWLINE)
        start = end


def _summarize_fasta_stripped_warning(stripped_counts: dict[int, int]) -> list[str]:
    """把 FASTA 非法字符剥离统计整理成警告文本。"""
    total = 0
    for count in stripped_counts.values():
        total += count

    if total == 0:
        return []

    parts: list[str] = []
    for symbol in sorted(stripped_counts):
        count = stripped_counts[symbol]
        parts.append(f"{chr(symbol)}({count})")

    warning_1 = (
        f"WARNING: {total} invalid characters stripped from FASTA file: "
        + " ".join(parts)
    )
    warning_2 = "REMINDER: vsearch does not support amino acid sequences"
    return [warning_1, warning_2]


def _detect_input_format(reader: BinaryLineReader) -> str:
    """检测输入是 FASTQ、FASTA 还是空文件。"""
    row = reader.readline()
    if row is None:
        return "empty"

    line_bytes, line_number = row
    reader.pushback(line_bytes, line_number)

    if line_bytes.startswith(b"@"):
        return "fastq"
    if line_bytes.startswith(b">"):
        return "fasta"

    raise StructuredFastxError(
        code="UNRECOGNIZED_INPUT_FORMAT",
        message="Unrecognized file type (not proper FASTA or FASTQ format)",
    )


def _validate_parameter_combination(
    params: FastxFilterInput,
    input_format: str,
) -> None:
    """复刻 fastx_filter 对 FASTA 输入的质量参数限制。"""
    if input_format == "fasta" and params.fastq_maxee_rate != -1:
        raise StructuredFastxError(
            code="FASTA_WITH_QUALITY_OPTIONS",
            message=(
                "The following options are not accepted with the fastx_filter "
                "command when the input is a FASTA file, because quality scores "
                "are not available: eeout, fastq_ascii, fastq_eeout, fastq_maxee, "
                "fastq_maxee_rate, fastq_minqual, fastq_out, fastq_qmax, fastq_qmin, "
                "fastq_truncee, fastq_truncee_rate, fastq_truncqual,  "
                "fastqout_discarded, fastqout_discarded_rev, fastqout_rev"
            ),
        )


def run(data: FastxFilterInput | dict) -> FastxFilterOutput:
    """Agent 调用入口。

    参数可以直接传 FastxFilterInput，也可以传普通字典。
    """
    try:
        if isinstance(data, FastxFilterInput):
            params = data
        else:
            params = FastxFilterInput.model_validate(data)
    except Exception as exc:
        stats = FastxFilterStats()
        return FastxFilterOutput(
            success=False,
            stats=stats,
            error=ErrorInfo(code="INPUT_VALIDATION_ERROR", message=str(exc)),
        )

    stats = FastxFilterStats()
    warnings: list[str] = []
    stripped_counts: dict[int, int] = {}
    input_handle: Optional[BinaryIO] = None
    output_handle: Optional[BinaryIO] = None
    input_format: Optional[str] = None

    try:
        if not params.fastaout:
            raise StructuredFastxError(
                code="NO_OUTPUT_FILES",
                message="No output files specified",
            )

        input_handle = _open_input_handle(params.input_path)
        reader = BinaryLineReader(input_handle)
        input_format = _detect_input_format(reader)

        _validate_parameter_combination(params, input_format)

        output_handle = _open_output_handle(params.fastaout)

        if input_format == "empty":
            return _to_output_model(
                success=True,
                stats=stats,
                warnings=warnings,
                output_path=params.fastaout,
                input_format=input_format,
            )

        while True:
            if input_format == "fastq":
                record = _parse_fastq_record(reader, warnings)
            else:
                record = _parse_fasta_record(reader, warnings, stripped_counts)

            if record is None:
                break

            stats.total_reads += 1
            analysis = _analyze_record(record, params)

            if analysis.failed_too_short:
                stats.failed_too_short += 1
            if analysis.failed_maxee_rate:
                stats.failed_maxee_rate += 1
            if analysis.failed_maxns:
                stats.failed_maxns += 1

            if analysis.discarded:
                stats.discarded_reads += 1
                continue

            stats.kept_reads += 1
            if analysis.truncated:
                stats.truncated_reads += 1

            kept_sequence = record.sequence[analysis.start : analysis.start + analysis.length]
            _write_fasta_record(output_handle, record.header, kept_sequence)

        if stats.total_reads > 0:
            stats.filtered_rate = (stats.kept_reads / stats.total_reads) * 100.0
        else:
            stats.filtered_rate = 0.0

        warnings.extend(_summarize_fasta_stripped_warning(stripped_counts))

        return _to_output_model(
            success=True,
            stats=stats,
            warnings=warnings,
            output_path=params.fastaout,
            input_format=input_format,
        )

    except StructuredFastxError as error:
        return _to_output_model(
            success=False,
            stats=stats,
            warnings=warnings,
            output_path=params.fastaout,
            input_format=input_format,
            error=error,
        )
    except OSError as error:
        structured_error = StructuredFastxError(
            code="OS_ERROR",
            message=str(error),
        )
        return _to_output_model(
            success=False,
            stats=stats,
            warnings=warnings,
            output_path=params.fastaout,
            input_format=input_format,
            error=structured_error,
        )
    finally:
        if output_handle is not None:
            output_handle.close()
        if input_handle is not None:
            input_handle.close()


def _build_parser() -> SafeArgumentParser:
    """构建命令行解析器。"""
    parser = SafeArgumentParser(
        prog="fastx_filter.py",
        description=(
            "单端 FASTA/FASTQ 过滤工具（vsearch fastx_filter 核心子集 Python 实现）。\n"
            "支持固定剪切、EE rate 过滤、N 过滤、最短长度过滤，以及 FASTA 输出。"
        ),
        epilog=(
            "命令行示例：\n"
            "  python fastx_filter.py --fastx_filter temp/all.fq "
            "--fastq_stripleft 29 --fastq_stripright 18 "
            "--fastq_maxee_rate 0.01 --fastaout temp/filtered_python.fa\n\n"
            "参数说明：\n"
            "  --fastq_maxee_rate -1 表示禁用 EE rate 过滤\n"
            "  --fastq_maxns -1 表示禁用 N 过滤\n"
            "  --fastq_minlen 和 --minlen 是同一个参数别名"
        ),
        formatter_class=argparse.RawTextHelpFormatter,
        add_help=True,
    )
    parser.add_argument(
        "--fastx_filter",
        dest="input_path",
        required=True,
        help="输入文件路径，支持 FASTQ / FASTA，也支持 .gz 压缩文件",
    )
    parser.add_argument(
        "--fastaout",
        dest="fastaout",
        required=True,
        help="输出 FASTA 文件路径，支持 .fa / .fasta / .gz",
    )
    parser.add_argument(
        "--fastq_stripleft",
        dest="fastq_stripleft",
        type=int,
        default=0,
        help="从序列左端固定剪掉多少个碱基，默认 0",
    )
    parser.add_argument(
        "--fastq_stripright",
        dest="fastq_stripright",
        type=int,
        default=0,
        help="从序列右端固定剪掉多少个碱基，默认 0",
    )
    parser.add_argument(
        "--fastq_maxee_rate",
        dest="fastq_maxee_rate",
        type=float,
        default=-1.0,
        help="最大平均期望错误率，默认 -1 表示禁用这个过滤条件",
    )
    parser.add_argument(
        "--fastq_maxns",
        dest="fastq_maxns",
        type=int,
        default=-1,
        help="允许的最大 N 碱基数量，默认 -1 表示禁用这个过滤条件",
    )
    parser.add_argument(
        "--fastq_minlen",
        "--minlen",
        dest="minlen",
        type=int,
        default=1,
        help="过滤后允许的最短序列长度，默认 1",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> FastxFilterOutput:
    """命令行入口。

    返回值仍然是结构化模型，方便直接被别的 Python 代码复用。
    """
    try:
        parser = _build_parser()
        namespace = parser.parse_args(argv)
        params = FastxFilterInput(
            input_path=namespace.input_path,
            fastaout=namespace.fastaout,
            fastq_stripleft=namespace.fastq_stripleft,
            fastq_stripright=namespace.fastq_stripright,
            fastq_maxee_rate=namespace.fastq_maxee_rate,
            fastq_maxns=namespace.fastq_maxns,
            minlen=namespace.minlen,
        )
        return run(params)
    except ArgumentParserError as exc:
        return FastxFilterOutput(
            success=False,
            stats=FastxFilterStats(),
            error=ErrorInfo(code="ARGPARSE_ERROR", message=str(exc)),
        )
    except Exception as exc:
        return FastxFilterOutput(
            success=False,
            stats=FastxFilterStats(),
            error=ErrorInfo(code="MAIN_ERROR", message=str(exc)),
        )


if __name__ == "__main__":
    result = main()
    print(result.model_dump_json(indent=2))
