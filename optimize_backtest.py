#!/usr/bin/env python3
"""MSTU 组合策略参数网格搜索。"""

import argparse
import itertools
import json
import os

from backtest import CombinedStrategy, download_market_data, collect_backtest_metrics


SEARCH_SPACE = {
    "gap_down_pct": [-0.03, -0.035, -0.04, -0.045],
    "dip_stop_pct": [0.015, 0.018, 0.02],
    "trade_amount": [250, 350, 450],
    "mom_trade_amount": [550, 650, 750],
    "gap_up_pct": [0.01, 0.012, 0.015],
    "max_chase_pct": [0.03, 0.035, 0.04],
    "vwap_volume_ratio_min": [1.0, 1.2, 1.4],
    "rsi_rebound_prev_max": [20, 22, 25],
    "kdj_turn_level": [25, 30, 35],
    "bull_structure_confirm_bars": [2, 3, 4],
}


def generate_param_sets(limit=None):
    keys = list(SEARCH_SPACE.keys())
    values = [SEARCH_SPACE[key] for key in keys]
    count = 0
    for combo in itertools.product(*values):
        params = dict(zip(keys, combo))
        count += 1
        if limit is not None and count > limit:
            break
        yield params


def score_result(result: dict) -> tuple:
    """排序时优先收益，其次控制回撤，再看胜率。"""
    drawdown_penalty = result["max_drawdown"] if result["max_drawdown"] is not None else 999
    return (result["return_pct"], -drawdown_penalty, result["win_rate"])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--interval", default="15m", help="数据周期，默认15m")
    parser.add_argument("--period", default="60d", help="历史范围，默认60d")
    parser.add_argument("--download", action="store_true", help="重新下载数据")
    parser.add_argument("--limit", type=int, default=120, help="最多搜索多少组参数")
    parser.add_argument("--top", type=int, default=10, help="输出前几组结果")
    args = parser.parse_args()

    csv_path = {
        "mstu": os.path.join(os.path.dirname(__file__), "mstu_history.csv"),
        "mstr": os.path.join(os.path.dirname(__file__), "mstr_history.csv"),
    }
    if args.download or not (os.path.exists(csv_path["mstu"]) and os.path.exists(csv_path["mstr"])):
        result = download_market_data(interval=args.interval, period=args.period)
        if result:
            csv_path = result
        else:
            raise SystemExit("无法下载回测数据")

    results = []
    for idx, params in enumerate(generate_param_sets(limit=args.limit), start=1):
        metrics = collect_backtest_metrics(
            CombinedStrategy,
            csv_path=csv_path,
            strategy_params=params,
        )
        row = {**params, **metrics}
        results.append(row)
        print(
            f"[{idx}] return={metrics['return_pct']:+.2f}% "
            f"dd={metrics['max_drawdown']}% win={metrics['win_rate']:.1f}% "
            f"params={params}"
        )

    results.sort(key=score_result, reverse=True)
    top_results = results[:args.top]

    print(f"\n=== Top {len(top_results)} 参数组合 ===")
    for idx, row in enumerate(top_results, start=1):
        params = {key: row[key] for key in SEARCH_SPACE}
        print(
            f"{idx}. return={row['return_pct']:+.2f}% final=${row['final_value']:.2f} "
            f"dd={row['max_drawdown']}% win={row['win_rate']:.1f}% trades={row['total_closed']} "
            f"params={params}"
        )

    output_path = os.path.join(os.path.dirname(__file__), "optimization_results.json")
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n结果已保存: {output_path}")


if __name__ == "__main__":
    main()
