"""B-side platform service: accounts, chat, workflows, schedules, notifications."""

# 包导出保留已有兼容入口, 具体服务仍由 assembly 显式装配。
__all__ = ["app", "assembly", "auth", "chat_runner", "config", "errors", "identity", "queue", "repositories", "runtime_client", "scheduling"]
