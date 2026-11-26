"""Match names in a cast field, never in the title or surrounding page."""
import re
import unicodedata

OFFICIAL_PROFILES = {
    "maison": ("https://profile.yoshimoto.co.jp/talent/detail?id=8835", ["吉野おいなり君", "めぞん吉野", "めぞん 吉野", "原一刻", "めぞん原"]),
    "nansui": ("https://profile.yoshimoto.co.jp/talent/detail?id=8902", ["大川内聡", "軟水大川内", "軟水 大川内", "つるまる", "軟水つるまる"]),
    "pyuto": ("https://profile.yoshimoto.co.jp/talent/detail?id=8773", ["ピュートポイント", "ピュート ポイント", "ポイント（ピュート）", "竹内智也", "ピュート竹内", "ピュート 竹内"]),
}

ROLES = re.compile(r"(?:出演者?|ゲスト|MC|司会|進行|前説|ナレーション)\s*[:：]", re.I)


def normalized_name(value):
    text = unicodedata.normalize("NFKC", value)
    text = "".join(chr(ord(c) - 96) if "ァ" <= c <= "ヶ" else c for c in text)
    return "".join(text.casefold().split())


def cast_matches(fields, performer):
    individual_names = OFFICIAL_PROFILES.get(performer.get("id"), ("", []))[1]
    aliases = {normalized_name(name) for name in
               [performer["name"], *individual_names, *performer.get("aliases", [])]}
    if isinstance(fields, str):
        fields = [fields]
    for field in fields or ():
        text = ROLES.sub("/", unicodedata.normalize("NFKC", field))
        for part in re.split(r"[/、,・\n;|]+", text):
            part = re.sub(r"^\s*\[(?:企画ライブ|ネタ&コーナーライブ|ネタライブ)\]\s*", "", part)
            name = re.sub(r"\s*\([^()]*\)\s*$", "", part)
            if normalized_name(part) in aliases or normalized_name(name) in aliases:
                return True
    return False
