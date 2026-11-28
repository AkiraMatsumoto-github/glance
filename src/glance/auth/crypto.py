"""更新トークンの暗号化（technical_design.md §5）。

鍵は GLANCE_TOKEN_KEY（Fernet）。鍵を入れ替えるときは「新しい鍵,古い鍵」と並べる。
暗号化は先頭の鍵で行い、復号は並べたどの鍵でもできる。古い鍵で暗号化した値は、python -m glance.rekey で
新しい鍵で暗号化し直す（その後に古い鍵を外せる）。
"""

from cryptography.fernet import Fernet, InvalidToken, MultiFernet


class TokenCipher:
    def __init__(self, keys: str) -> None:
        parts = [k.strip() for k in keys.split(",") if k.strip()]
        if not parts:
            raise ValueError("GLANCE_TOKEN_KEY が空です")
        self._fernet = MultiFernet([Fernet(k) for k in parts])
        self._current = Fernet(parts[0])

    def encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode()).decode()

    def decrypt(self, value: str) -> str:
        return self._fernet.decrypt(value.encode()).decode()

    def is_current(self, value: str) -> bool:
        """先頭の（いま暗号化に使う）鍵で暗号化した値か。"""
        try:
            self._current.decrypt(value.encode())
        except InvalidToken:
            return False
        return True

    def rotate(self, value: str) -> str:
        """並べたどれかの鍵で復号し、先頭の鍵で暗号化し直す。どの鍵でも復号できなければ InvalidToken。"""
        return self._fernet.rotate(value.encode()).decode()
