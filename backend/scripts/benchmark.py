"""并发访问压力测试（结题报告"并发访问控制"部分的实验数据来源）。

只用 Python 标准库，无需额外安装（装了 matplotlib 会自动出图）。

用法（后端已启动，并且至少有一个训练好的模型）：
    python scripts/benchmark.py --model 1
    python scripts/benchmark.py --model 1 --levels 1 2 4 8 16 32 --duration 10 --batch 1

测试内容：
  实验1  并发性能：不同并发数下的吞吐量（QPS）与延迟（P50/P95/P99）
  实验2  限流验证：API Key 限额 60 次/分钟，瞬间发送 120 个请求，统计 200 / 429 数量
  实验3  并发闸门：高并发 + 大批量请求，观察排队、峰值并发与 503 拒绝情况
结果保存在 backend/benchmark_results/ 下（CSV + PNG + Markdown 汇总）。
"""
from __future__ import annotations

import argparse
import json
import statistics
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "benchmark_results"


def http(method: str, url: str, body: dict | None = None, headers: dict | None = None, timeout: float = 120):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            payload = r.read()
            return r.status, (time.perf_counter() - t0) * 1000, payload
    except urllib.error.HTTPError as e:
        return e.code, (time.perf_counter() - t0) * 1000, e.read()
    except Exception as e:  # 连接错误等
        return 0, (time.perf_counter() - t0) * 1000, str(e).encode()


def pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    return round(s[min(len(s) - 1, int(p * len(s)))], 2)


def login(base: str, user: str, pwd: str) -> str:
    code, _, body = http("POST", f"{base}/api/v1/auth/login", {"username": user, "password": pwd})
    if code != 200:
        raise SystemExit(f"登录失败（{code}）：{body.decode('utf-8', 'ignore')}")
    return json.loads(body)["access_token"]


def make_key(base: str, token: str, name: str, limit: int) -> tuple[int, str]:
    code, _, body = http("POST", f"{base}/api/v1/keys", {"name": name, "rate_limit_per_min": limit},
                         {"Authorization": f"Bearer {token}"})
    if code == 422 and limit > 6000:
        # 兼容旧版后端（限额上限 6000 次/分钟 = 100 次/秒，对压测仍然足够）
        code, _, body = http("POST", f"{base}/api/v1/keys", {"name": name, "rate_limit_per_min": 6000},
                             {"Authorization": f"Bearer {token}"})
    if code != 200:
        raise SystemExit(f"创建 API Key 失败（{code}）：{body.decode('utf-8', 'ignore')}（需要管理员账号）")
    d = json.loads(body)
    return d["id"], d["api_key"]


def del_key(base: str, token: str, key_id: int) -> None:
    http("DELETE", f"{base}/api/v1/keys/{key_id}", headers={"Authorization": f"Bearer {token}"})


def run_load(url: str, key: str, payload: dict, concurrency: int, duration: float) -> dict:
    stop = time.perf_counter() + duration
    lat: list[float] = []
    codes: dict[int, int] = {}
    lock = threading.Lock()

    def worker() -> None:
        while time.perf_counter() < stop:
            code, ms, _ = http("POST", url, payload, {"X-API-Key": key})
            with lock:
                codes[code] = codes.get(code, 0) + 1
                if code == 200:
                    lat.append(ms)

    t0 = time.perf_counter()
    threads = [threading.Thread(target=worker) for _ in range(concurrency)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    elapsed = time.perf_counter() - t0
    ok = codes.get(200, 0)
    return {
        "concurrency": concurrency,
        "requests": sum(codes.values()),
        "success": ok,
        "qps": round(ok / elapsed, 2),
        "p50_ms": pct(lat, 0.5),
        "p95_ms": pct(lat, 0.95),
        "p99_ms": pct(lat, 0.99),
        "mean_ms": round(statistics.mean(lat), 2) if lat else 0,
        "codes": codes,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="预测服务并发压测")
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--user", default="admin")
    ap.add_argument("--password", default="admin123")
    ap.add_argument("--model", type=int, required=True, help="要压测的模型 ID")
    ap.add_argument("--levels", type=int, nargs="+", default=[1, 2, 4, 8, 16, 32])
    ap.add_argument("--duration", type=float, default=10, help="每个并发等级持续秒数")
    ap.add_argument("--batch", type=int, default=1, help="每个请求包含的样本条数")
    ap.add_argument("--skip", nargs="*", default=[], help="跳过的实验编号，如 --skip 3")
    args = ap.parse_args()

    OUT.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    token = login(args.base, args.user, args.password)
    code, _, body = http("GET", f"{args.base}/api/v1/models/{args.model}/schema",
                         headers={"Authorization": f"Bearer {token}"})
    if code != 200:
        raise SystemExit(f"获取模型 {args.model} 失败：{body.decode('utf-8', 'ignore')}")
    schema = json.loads(body)
    record = schema["example_request"]["records"][0]
    url = f"{args.base}/api/v1/models/{args.model}/predict"
    print(f"压测模型：#{args.model} {schema['name']}")
    report = [f"# 预测服务并发压测报告（{stamp}）", "", f"- 模型：#{args.model} {schema['name']}",
              f"- 服务地址：{args.base}", f"- 每请求样本数：{args.batch}", ""]

    # ---------------- 实验1 ----------------
    if "1" not in args.skip:
        print("\n实验1：并发性能测试")
        kid, key = make_key(args.base, token, "压测-高限额", 1_000_000)
        payload = {"records": [record] * args.batch}
        rows = []
        try:
            for c in args.levels:
                r = run_load(url, key, payload, c, args.duration)
                rows.append(r)
                print(f"  并发 {c:>3}: QPS={r['qps']:>8}  P50={r['p50_ms']:>8}ms  P95={r['p95_ms']:>8}ms  "
                      f"P99={r['p99_ms']:>8}ms  状态码={r['codes']}")
        finally:
            del_key(args.base, token, kid)
        csv = OUT / f"exp1_concurrency_{stamp}.csv"
        with open(csv, "w", encoding="utf-8-sig") as f:
            f.write("并发数,请求数,成功数,QPS,P50(ms),P95(ms),P99(ms),平均(ms),状态码分布\n")
            for r in rows:
                f.write(f"{r['concurrency']},{r['requests']},{r['success']},{r['qps']},{r['p50_ms']},{r['p95_ms']},"
                        f"{r['p99_ms']},{r['mean_ms']},\"{r['codes']}\"\n")
        report += ["## 实验1 并发性能", "", "| 并发数 | 请求数 | 成功 | QPS | P50 (ms) | P95 (ms) | P99 (ms) |",
                   "|---|---|---|---|---|---|---|"]
        report += [f"| {r['concurrency']} | {r['requests']} | {r['success']} | {r['qps']} | {r['p50_ms']} | "
                   f"{r['p95_ms']} | {r['p99_ms']} |" for r in rows]
        try:
            import matplotlib

            matplotlib.use("Agg")
            import matplotlib.pyplot as plt

            plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
            plt.rcParams["axes.unicode_minus"] = False
            fig, ax1 = plt.subplots(figsize=(7, 4.2), dpi=150)
            xs = [r["concurrency"] for r in rows]
            ax1.plot(xs, [r["qps"] for r in rows], "o-", color="#2563eb", label="吞吐量 QPS")
            ax1.set_xlabel("并发请求数")
            ax1.set_ylabel("QPS（次/秒）")
            ax1.set_xscale("log", base=2)
            ax2 = ax1.twinx()
            ax2.plot(xs, [r["p50_ms"] for r in rows], "s--", color="#16a34a", label="P50 延迟")
            ax2.plot(xs, [r["p95_ms"] for r in rows], "^--", color="#dc2626", label="P95 延迟")
            ax2.set_ylabel("延迟（ms）")
            lines = ax1.get_legend_handles_labels()[0] + ax2.get_legend_handles_labels()[0]
            labels = ax1.get_legend_handles_labels()[1] + ax2.get_legend_handles_labels()[1]
            ax1.legend(lines, labels, loc="upper left", fontsize=8)
            ax1.set_title(f"不同并发数下的预测服务性能（{schema['name']}）", fontsize=10)
            fig.tight_layout()
            png = OUT / f"exp1_concurrency_{stamp}.png"
            fig.savefig(png)
            report += ["", f"![并发性能]({png.name})"]
            print(f"  图表：{png}")
        except ImportError:
            print("  （未安装 matplotlib，跳过出图）")
        report.append("")

    # ---------------- 实验2 ----------------
    if "2" not in args.skip:
        print("\n实验2：限流验证（限额 60 次/分钟，瞬间发送 120 个请求）")
        kid, key = make_key(args.base, token, "压测-限流验证", 60)
        payload = {"records": [record]}
        try:
            with ThreadPoolExecutor(max_workers=12) as ex:
                results = list(ex.map(lambda _: http("POST", url, payload, {"X-API-Key": key}), range(120)))
        finally:
            del_key(args.base, token, kid)
        codes: dict[int, int] = {}
        for c, _, _ in results:
            codes[c] = codes.get(c, 0) + 1
        print(f"  状态码分布：{codes}（200=放行，429=被限流）")
        report += ["## 实验2 限流验证", "", "API Key 限额 60 次/分钟（令牌桶），瞬间并发发送 120 个请求：", "",
                   "| 状态码 | 数量 | 含义 |", "|---|---|---|"]
        meaning = {200: "放行", 429: "超过限额被拒绝", 503: "并发闸门排队超时"}
        report += [f"| {c} | {n} | {meaning.get(c, '')} |" for c, n in sorted(codes.items())]
        report.append("")

    # ---------------- 实验3 ----------------
    if "3" not in args.skip:
        print("\n实验3：并发闸门（64 并发 × 每请求 2000 条样本）")
        kid, key = make_key(args.base, token, "压测-并发闸门", 1_000_000)
        try:
            r = run_load(url, key, {"records": [record] * 2000}, 64, max(args.duration, 10))
        finally:
            del_key(args.base, token, kid)
        _, _, sbody = http("GET", f"{args.base}/api/v1/stats/system", headers={"Authorization": f"Bearer {token}"})
        gate = json.loads(sbody).get("predict_gate", {})
        print(f"  状态码：{r['codes']}  服务端峰值并发={gate.get('peak_active')}（上限 {gate.get('limit')}）"
              f"  闸门累计拒绝={gate.get('rejected')}")
        report += ["## 实验3 并发闸门", "",
                   f"64 个客户端同时发送大批量请求（每请求 2000 条），服务端同时执行的预测数被限制在 "
                   f"{gate.get('limit')} 以内，其余请求排队；排队超过设定时间返回 503。", "",
                   f"- 客户端状态码分布：{r['codes']}",
                   f"- 服务端峰值并发：{gate.get('peak_active')} / 上限 {gate.get('limit')}",
                   f"- 成功请求 P50 / P95 延迟：{r['p50_ms']} / {r['p95_ms']} ms", ""]

    md = OUT / f"benchmark_report_{stamp}.md"
    md.write_text("\n".join(report), encoding="utf-8")
    print(f"\n汇总报告：{md}")


if __name__ == "__main__":
    main()
