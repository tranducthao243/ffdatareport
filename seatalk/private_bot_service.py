from __future__ import annotations

from typing import Any

from .identity import build_unified_user


def is_authorized_private_sender(runtime: dict[str, Any], callback_context: dict[str, str]) -> bool:
    directory = runtime.get("user_directory") or []
    env_directory = runtime.get("env_role_directory") or []
    if not directory and not env_directory:
        return True
    unified_user = build_unified_user(callback_context, directory, env_directory=env_directory)
    return unified_user["role"] in {"admin", "superadmin"}


def format_private_access_denied(callback_context: dict[str, str], *, contact_email: str) -> str:
    return (
        "**Bot chỉ nhận lệnh private từ admin đã được cấp quyền.**\n"
        f"*Vui lòng liên hệ {contact_email} để được thêm quyền.*\n"
        "\n"
        "*Thông tin định danh hiện tại của bạn:*\n"
        f"- employee_code: `{callback_context.get('employee_code') or '-'}`\n"
        f"- email: `{callback_context.get('email') or '-'}`\n"
        f"- seatalk_id: `{callback_context.get('seatalk_id') or '-'}`"
    )


def build_private_help_text(role: str) -> str:
    lines = [
        "**LỆNH BOT PRIVATE**",
        "*Gõ `.` để mở nhanh menu này.*",
        "",
    ]
    if role == "superadmin":
        lines.extend(
            [
                "**Kiểm tra dữ liệu**",
                "- `health`: tổng quan tình trạng dữ liệu",
                "- `data`: kho dữ liệu đang dùng",
                "- `scope`: source scope hiện tại",
                "",
            ]
        )
    lines.extend(
        [
            "**Tiện ích**",
            "- `web`: liệt kê các link web quan trọng của team",
            "- `hashtag`: gõ hashtag và tên hashtag để check data",
            "- `kol`: gõ `kol <tên KOL>` để check data theo KOL",
            "",
            "**Dữ liệu KOLs**",
            "- `campaign`: báo cáo campaign hiện tại",
            "- `official`: báo cáo kênh Official",
            "- `dance`: báo cáo video trend nhảy",
            "- `roblox`: báo cáo TOP video Roblox",
            "",
            "**Tính năng khác**",
            "- `imagelink`: tải ảnh lên web nội bộ và trả link ảnh",
            "- `removebg`: tách nền ảnh và trả lại ảnh",
            "- `shortlink`: tạo shortlink từ link và config",
            "- `enhanceimage`: làm nét ảnh rồi trả kết quả",
            "",
            "**Hướng dẫn**",
            "- `help`: xem cách dùng bot",
        ]
    )
    return "\n".join(lines)


def build_private_usage_text() -> str:
    return (
        "**HƯỚNG DẪN SỬ DỤNG BOT**\n"
        "\n"
        "- Gõ dấu chấm `.` để gọi bảng tính năng.\n"
        "- Chỉ cần gõ lệnh là có thể gọi được dữ liệu hoặc nhờ bot giải quyết các vấn đề cần thiết.\n"
        "- Dự kiến BOT sẽ cập nhật thêm nhiều tính năng hơn nữa.\n"
        "- Dữ liệu từ hệ thống của Free Fire.\n"
        "- Nếu bạn có góp ý gì vui lòng liên hệ superadmin `ducthao.tran@garena.vn`."
    )
