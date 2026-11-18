"""外部终端调用示例：任何能发 HTTP 请求的程序（Python 脚本、Excel/VBA、MATLAB、LabVIEW、手机 App）
都可以用同样的方式调用平台的预测服务。

1. 在网页「API 接入」页面创建 API Key
2. 在「模型仓库」中把要用的模型设为"已发布"，记下模型 ID
3. 修改下面的 BASE / API_KEY / MODEL_ID 后运行：python api_client_example.py
"""
import json
import urllib.request

BASE = "http://127.0.0.1:8000/api/v1"  # 局域网内其他电脑访问时，换成服务器的 IP
API_KEY = "upk_在这里填你的API Key"
MODEL_ID = 1


def call(method: str, path: str, body: dict | None = None) -> dict:
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode("utf-8") if body else None,
        method=method,
        headers={"X-API-Key": API_KEY, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


if __name__ == "__main__":
    # ① 查询模型需要哪些输入字段
    schema = call("GET", f"/models/{MODEL_ID}/schema")
    print("模型：", schema["name"], "  预测目标：", schema["target"])
    for f in schema["inputs"]:
        print(f"  - {f['name']}（{f['type']}）默认值 {f.get('default')}")

    # ② 发送预测请求（这里直接用默认值示例；实际使用时替换成自己的数据，可一次发送多条）
    body = schema["example_request"]
    body["explain"] = True
    result = call("POST", f"/models/{MODEL_ID}/predict", body)
    print("\n预测结果：", result["predictions"], f"（耗时 {result['latency_ms']} ms）")
    if result.get("explanations"):
        print("各特征对这次预测的贡献：")
        for c in result["explanations"][0]["contributions"]:
            print(f"  {c['feature']:<12} {c['contribution']:+.4f}")
