from __future__ import annotations

import argparse
import asyncio
import json
from ipaddress import ip_address
from urllib.parse import urlsplit

import httpx


def validate_public_url(value: str) -> str:
    normalized = value.rstrip("/")
    parsed = urlsplit(normalized)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("公开地址必须是无凭据的 HTTPS 域名")
    if parsed.path or parsed.query or parsed.fragment:
        raise ValueError("公开地址只能包含协议和域名，不能包含路径、查询或片段")
    if parsed.hostname in {"localhost", "teacher.example.invalid"}:
        raise ValueError("公开地址不能使用本机或占位域名")
    try:
        ip_address(parsed.hostname)
    except ValueError:
        pass
    else:
        raise ValueError("公开地址必须使用域名，不能直接使用 IP")
    return normalized


def validate_security_headers(headers: httpx.Headers) -> list[str]:
    errors: list[str] = []
    required = {
        "strict-transport-security": "max-age=",
        "content-security-policy": "default-src",
        "x-content-type-options": "nosniff",
        "x-frame-options": "deny",
        "referrer-policy": "same-origin",
    }
    for name, expected in required.items():
        if expected not in headers.get(name, "").lower():
            errors.append(f"响应头 {name} 缺失或不符合预期")
    return errors


def validate_registration(payload: object, expect_open: bool) -> list[str]:
    if not isinstance(payload, dict):
        return ["注册配置响应不是 JSON 对象"]
    errors: list[str] = []
    if payload.get("enabled") is not expect_open:
        errors.append("注册开放状态与验收参数不一致")
    if expect_open:
        if payload.get("invite_required") is not True:
            errors.append("生产注册未强制邀请码")
        contact = payload.get("support_contact")
        if not isinstance(contact, str) or len(contact.strip()) < 5:
            errors.append("公开注册缺少真实支持联系方式")
    return errors


async def verify(base_url: str, expect_open: bool) -> dict[str, object]:
    errors: list[str] = []
    async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
        home = await client.get(base_url)
        if home.status_code != 200:
            errors.append(f"首页返回 {home.status_code}，预期 200")
        errors.extend(validate_security_headers(home.headers))
        for path in ("/api/health/live", "/api/health/ready"):
            response = await client.get(base_url + path)
            if response.status_code != 200:
                errors.append(f"{path} 返回 {response.status_code}，预期 200")
        registration = await client.get(base_url + "/api/v1/auth/registration")
        if registration.status_code != 200:
            errors.append(f"注册配置返回 {registration.status_code}，预期 200")
        else:
            try:
                payload = registration.json()
            except ValueError:
                payload = None
            errors.extend(validate_registration(payload, expect_open))
    return {"status": "ok" if not errors else "failed", "base_url": base_url, "errors": errors}


def main() -> int:
    parser = argparse.ArgumentParser(description="从公网侧验证 HTTPS、健康检查和注册门槛")
    parser.add_argument("url", help="例如 https://teacher.example.com")
    parser.add_argument(
        "--expect-registration",
        choices=("closed", "invite"),
        default="closed",
    )
    args = parser.parse_args()
    try:
        base_url = validate_public_url(args.url)
        result = asyncio.run(verify(base_url, args.expect_registration == "invite"))
    except (ValueError, httpx.HTTPError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
