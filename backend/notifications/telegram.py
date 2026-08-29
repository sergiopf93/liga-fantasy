"""
Notificaciones vía Telegram Bot.
Envía alertas de mercado e informes diarios.
"""
from __future__ import annotations

import logging
from typing import Optional

import requests

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"


class TelegramNotifier:
    """
    Envía mensajes a un chat/canal de Telegram.

    Configuración necesaria (en config.yaml o variables de entorno):
      TELEGRAM_TOKEN: token del bot (obtenido desde @BotFather)
      TELEGRAM_CHAT_ID: ID del chat/canal destino
    """

    MAX_MESSAGE_LEN = 4096

    def __init__(self, token: str, chat_id: str):
        self.token = token
        self.chat_id = chat_id
        self._session = requests.Session()

    def send(self, text: str, parse_mode: str = "Markdown") -> bool:
        """Envía un mensaje de texto. Retorna True si se envió correctamente."""
        # Telegram limita a 4096 chars → dividir si es necesario
        chunks = self._split(text)
        success = True
        for chunk in chunks:
            ok = self._send_chunk(chunk, parse_mode)
            success = success and ok
        return success

    def send_report(self, report_text: str) -> bool:
        """Envía el informe diario formateado."""
        return self.send(report_text)

    def send_alert(self, message: str) -> bool:
        """Envía una alerta breve."""
        return self.send(f"🚨 *Alerta Fantasy*\n{message}")

    def _send_chunk(self, text: str, parse_mode: str) -> bool:
        url = TELEGRAM_API.format(token=self.token, method="sendMessage")
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }
        try:
            resp = self._session.post(url, json=payload, timeout=15)
            if not resp.ok:
                logger.error("Telegram error %d: %s", resp.status_code, resp.text[:200])
                return False
            return True
        except requests.RequestException as exc:
            logger.error("Error enviando a Telegram: %s", exc)
            return False

    def _split(self, text: str) -> list[str]:
        if len(text) <= self.MAX_MESSAGE_LEN:
            return [text]
        chunks = []
        while text:
            if len(text) <= self.MAX_MESSAGE_LEN:
                chunks.append(text)
                break
            # Cortar en salto de línea más cercano al límite
            cut = text.rfind("\n", 0, self.MAX_MESSAGE_LEN)
            if cut == -1:
                cut = self.MAX_MESSAGE_LEN
            chunks.append(text[:cut])
            text = text[cut:].lstrip("\n")
        return chunks

    @classmethod
    def from_env(cls) -> "TelegramNotifier":
        import os
        token = os.environ.get("TELEGRAM_TOKEN", "")
        chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
        if not token or not chat_id:
            raise ValueError(
                "Variables TELEGRAM_TOKEN y TELEGRAM_CHAT_ID no están configuradas. "
                "Añádelas en config/config.yaml o como variables de entorno."
            )
        return cls(token=token, chat_id=chat_id)
