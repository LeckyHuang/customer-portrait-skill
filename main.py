#!/usr/bin/env python3
"""CLI 入口（本地调试用）"""
import argparse
import json
import sys
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

from src.config import load_config
from src.schemas import CustomerInput
from src.llm import create_llm
from src.search import create_searchers
from src.engine import PortraitEngine


def parse_args():
    p = argparse.ArgumentParser(description="客户画像生成引擎")
    p.add_argument("--config", default="config.yaml")
    p.add_argument("--input", help="输入 JSON 文件")
    p.add_argument("--org", help="客户单位名称")
    p.add_argument("--industry", help="所属行业")
    p.add_argument("--guest", help="主宾姓名")
    p.add_argument("--needs", help="参观需求")
    p.add_argument("--output", help="输出 JSON 文件")
    p.add_argument("--pretty", action="store_true")
    return p.parse_args()


def build_customer(args) -> CustomerInput:
    if args.input:
        data = json.loads(Path(args.input).read_text(encoding="utf-8"))
        return CustomerInput(**data)
    if not all([args.org, args.industry, args.guest, args.needs]):
        print("错误：需要 --org/--industry/--guest/--needs 或 --input", file=sys.stderr)
        sys.exit(1)
    return CustomerInput(
        org_name=args.org, industry=args.industry,
        guest_name=args.guest, visit_needs=args.needs,
    )


def main():
    args = parse_args()
    config = load_config(args.config)
    customer = build_customer(args)
    llm = create_llm(config["llm"])
    searchers = create_searchers(config["search"])
    engine = PortraitEngine(config, llm, searchers)

    print(f"[开始] {customer.org_name} · {customer.guest_name}", file=sys.stderr)
    result = engine.run(customer)

    if result.error:
        print(f"[错误] {result.error}", file=sys.stderr)
        sys.exit(1)

    print(
        f"[完成] 搜索 {len(result.queries_executed)} 次 | "
        f"可信度 {result.confidence_assessment.get('overall', '?')}",
        file=sys.stderr,
    )
    output = {
        "portrait": result.portrait,
        "confidence_assessment": result.confidence_assessment,
        "sources": result.sources,
        "queries_executed": result.queries_executed,
    }
    text = json.dumps(output, ensure_ascii=False, indent=2 if args.pretty else None)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"[输出] 已写入 {args.output}", file=sys.stderr)
    else:
        print(text)


if __name__ == "__main__":
    main()
