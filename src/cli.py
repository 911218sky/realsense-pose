import argparse
from realsense_pose_extractor import processor_cli
from rehab_analyzer import analyzer_cli

def main():
    parser = argparse.ArgumentParser(
        description="全流程主 CLI: 姿勢擷取 (extract) 或 復健分析 (analyze)"
    )

    sub = parser.add_subparsers(dest="command", required=True)

    # extract 命令
    p1 = sub.add_parser("extract", help="執行姿勢擷取")
    p1.add_argument("--bag", help="Path to .bag file", required=True)
    p1.add_argument("--output", help="Output directory", default="./outputs")
    p1.add_argument("--tag", help="Prefix tag to be added to all output file names", default=None)
    p1.add_argument("--config", help="Optional YAML config", default=None)
    p1.set_defaults(func=processor_cli)

    # analyze 命令
    p2 = sub.add_parser("analyze", help="執行復健分析")
    p2.add_argument("--npy", help="Path to input .npy", required=True)
    p2.add_argument("--output", help="Output directory for results", default="./outputs")
    p2.add_argument("--tag", help="Prefix tag to be added to all output file names", default=None)
    p2.add_argument("--config", help="Optional YAML config", default=None)
    p2.set_defaults(func=analyzer_cli)

    args = parser.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()