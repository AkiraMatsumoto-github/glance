"""更新トークンの暗号化（technical_design.md §5）。

鍵は GLANCE_TOKEN_KEY（Fernet）。鍵を入れ替えるときは「新しい鍵,古い鍵」と並べる。
暗号化は先頭の鍵で行い、復号は並べたどの鍵でもできる。
"""

from cryptography.fernet import Fernet, MultiFernet


class TokenCipher:
    def __init__(self, keys: str) -> None:
        parts = [k.strip() for k in keys.split(",") if k.strip()]
        if not parts:
            raise ValueError("GLANCE_TOKEN_KEY が空です")
        self._fernet = MultiFernet([Fernet(k) for k in parts])

    def encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode()).decode()

    def decrypt(self, value: str) -> str:
        return self._fernet.decrypt(value.encode()).decode()
