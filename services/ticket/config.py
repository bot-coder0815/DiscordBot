import json
import os
from typing import Any, Optional


class TicketEmbedConfig:
    def __init__(self, data: dict) -> None:
        self.title: str = data.get("title", "Ticket")
        self.description: str = data.get("description", "")
        raw_color: str = data.get("color", "#3498db")
        self.color: int = int(raw_color.lstrip("#"), 16) if raw_color.startswith("#") else int(raw_color)
        self.footer: str = data.get("footer", "")

    def format_description(self, **kwargs: Any) -> str:
        return self.description.format(**kwargs)

    def format_footer(self, **kwargs: Any) -> str:
        return self.footer.format(**kwargs)


class TicketButtonConfig:
    def __init__(self, data: dict) -> None:
        self.label: str = data.get("label", "Button")
        self.emoji: str = data.get("emoji", "")
        self.custom_id: str = data.get("custom_id", "")
        self.style: str = data.get("style", "primary")


class TicketWarningConfig:
    def __init__(self, data: dict) -> None:
        self.threshold_hours: float = float(data.get("threshold_hours", 1))
        self.key: str = data.get("key", "")
        self.message: str = data.get("message", "")


class TicketInactivityConfig:
    def __init__(self, data: dict) -> None:
        self.enabled: bool = data.get("enabled", True)
        self.check_interval_seconds: int = data.get("check_interval_seconds", 1800)
        self.limit_seconds: int = data.get("limit_seconds", 172800)
        self.warnings: list[TicketWarningConfig] = [
            TicketWarningConfig(w) for w in data.get("warnings", [])
        ]


class TicketChannelConfig:
    def __init__(self, data: dict) -> None:
        self.naming_pattern: str = data.get("naming_pattern", "ticket-{name}-{number}")
        self.category_select_timeout_seconds: int = data.get("category_select_timeout_seconds", 300)
        self.category_select_placeholder: str = data.get("category_select_placeholder", "Select a topic...")
        self.category_select_prompt: str = data.get("category_select_prompt", "📋 **Please select a topic for your ticket:**")
        self.category_select_timeout_dm: str = data.get("category_select_timeout_dm", "Please select a topic...")


class TicketMessagesConfig:
    def __init__(self, data: dict) -> None:
        self.topic_set: str = data.get("topic_set", "Topic set to **{label}**!")
        self.dashboard_close: str = data.get("dashboard_close", "📝 Ticket closed via Dashboard.")
        self.transcript_gist_description: str = data.get("transcript_gist_description", "Ticket Transcript – {channel_name}")


class TicketTimingsConfig:
    def __init__(self, data: dict) -> None:
        self.delete_delay_seconds: int = data.get("delete_delay_seconds", 5)


class TicketFilesConfig:
    def __init__(self, data: dict) -> None:
        self.tickets_data: str = data.get("tickets_data", "tickets.json")
        self.transcripts_dir: str = data.get("transcripts_dir", "transcripts")


class TicketConfig:
    _instance: Optional["TicketConfig"] = None

    def __init__(self, path: str = "ticket_config.json") -> None:
        self._path = path
        raw = self._load_raw()
        self.files = TicketFilesConfig(raw.get("files", {}))
        self.inactivity = TicketInactivityConfig(raw.get("inactivity", {}))
        self.channel = TicketChannelConfig(raw.get("channel", {}))
        self.messages = TicketMessagesConfig(raw.get("messages", {}))
        self.timings = TicketTimingsConfig(raw.get("timings", {}))
        embeds_raw = raw.get("embeds", {})
        self.panel_embed = TicketEmbedConfig(embeds_raw.get("panel", {}))
        self.ticket_created_embed = TicketEmbedConfig(embeds_raw.get("ticket_created", {}))
        self.closing_embed = TicketEmbedConfig(embeds_raw.get("closing", {}))
        buttons_raw = raw.get("buttons", {})
        self.create_ticket_button = TicketButtonConfig(buttons_raw.get("create_ticket", {}))
        self.close_ticket_button = TicketButtonConfig(buttons_raw.get("close_ticket", {}))

    def _load_raw(self) -> dict:
        path = self._path
        if not os.path.isabs(path):
            script_dir = os.path.dirname(os.path.abspath(__file__))
            while not os.path.exists(os.path.join(script_dir, path)):
                parent = os.path.dirname(script_dir)
                if parent == script_dir:
                    break
                script_dir = parent
            path = os.path.join(script_dir, path)
        if not os.path.exists(path):
            path = self._path
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    @classmethod
    def get_instance(cls) -> "TicketConfig":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reload(cls) -> "TicketConfig":
        cls._instance = cls()
        return cls._instance

    def clear_instance(self) -> None:
        type(self)._instance = None
