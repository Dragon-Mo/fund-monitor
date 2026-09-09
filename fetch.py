# -*- coding: utf-8 -*-
"""Fetch formal fund NAV/history and each configured target ETF quote."""
import glob
import json
import re
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone


def http_get(url, headers=None, encoding="utf-8"):
    base = {"User-Agent": "Mozilla/5.0", "Referer": "https://fund.eastmoney.com/"}
    if headers:
        base.update(headers)
    try:
        request = urllib.request.Request(url, headers=base)
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.read().decode(encoding, "replace")
    except Exception as exc:
        print("request failed:", url, exc)
        return None


def load_profiles():
    profiles = []
    for path in sorted(glob.glob("data/*.json")):
        try:
            with open(path, "r", encoding="utf-8") as handle:
                profile = json.load(handle)
            if profile.get("funds"):
                profiles.append(profile)
        except Exception as exc:
            print("invalid profile:", path, exc)
    return profiles


def fetch_fund_history(code, rows=180):
    result = []
    page = 1
    while len(result) < rows and page <= 10:
        query = urllib.parse.urlencode({
            "callback": "", "fundCode": code, "pageIndex": page, "pageSize": 20
        })
        text = http_get("https://api.fund.eastmoney.com/f10/lsjz?" + query)
        if not text:
            break
        try:
            items = json.loads(text).get("Data", {}).get("LSJZList", []) or []
        except Exception:
            break
        if not items:
            break
        for item in items:
            try:
                result.append({
                    "date": item.get("FSRQ", ""),
                    "nav": float(item["DWJZ"]),
                    "pct": float(item.get("JZZZL") or 0),
                })
            except (KeyError, TypeError, ValueError):
                continue
        page += 1
    result.sort(key=lambda item: item["date"])
    return result[-rows:]


def fetch_etf_quotes(codes):
    if not codes:
        return {}
    text = http_get(
        "https://qt.gtimg.cn/q=" + ",".join(codes),
        {"Referer": "https://stockapp.finance.qq.com/"}, "gbk"
    )
    output = {}
    if not text:
        return output
    for line in text.splitlines():
        match = re.match(r'v_(\w+)="([^"]*)"', line.strip())
        if not match:
            continue
        fields = match.group(2).split("~")
        if len(fields) < 35:
            continue
        try:
            output[match.group(1)] = {
                "code": match.group(1), "name": fields[1],
                "price": float(fields[3] or 0), "prevClose": float(fields[4] or 0),
                "pct": float(fields[32] or 0), "high": float(fields[33] or 0),
                "low": float(fields[34] or 0), "time": fields[30],
            }
        except (ValueError, IndexError):
            continue
    return output


def main():
    profiles = load_profiles()
    configs = {}
    etf_codes = set()
    for profile in profiles:
        for config in profile.get("funds", []):
            configs.setdefault(config["code"], config)
            if config.get("etf_code"):
                etf_codes.add(config["etf_code"])

    quotes = fetch_etf_quotes(sorted(etf_codes))
    details = {}
    for code, config in configs.items():
        history = fetch_fund_history(code)
        latest = history[-1] if history else {}
        details[code] = {
            "code": code, "name": config.get("name", code),
            "nav": latest.get("nav"), "navDate": latest.get("date"),
            "navPct": latest.get("pct"), "history": history,
            "etfCode": config.get("etf_code", ""),
            "etfName": config.get("etf_name", ""),
            "etf": quotes.get(config.get("etf_code", "")),
            "defaults": config.get("defaults", {}),
        }

    users = [{
        "username": profile.get("username", "default"),
        "funds": [details[f["code"]] for f in profile.get("funds", []) if f["code"] in details]
    } for profile in profiles]

    now = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
    with open("docs/data.json", "w", encoding="utf-8") as handle:
        json.dump({"updated": now, "users": users}, handle, ensure_ascii=False)
    print("updated", now, "funds", len(details))


if __name__ == "__main__":
    main()
