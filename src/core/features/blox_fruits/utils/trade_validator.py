import re

from .trade_matcher import predict_trade_message, is_permanent_match, match_fruit_set
from .trade_extractor import extract_trade_details
from ....database.integrations.blox_fruits import BloxFruitsDatabase


def is_valid_trade_suggestor_format(message: str, db: BloxFruitsDatabase) -> bool:
    try:
        msg = message.lower().strip()
        trimmed = re.sub(r"(for\b.*?\bnlf\b).*", r"\1", msg)

        if "nlf" in trimmed:
            trimmed = trimmed[:trimmed.find("nlf")].strip()

        your_fruits, _, their_fruits, _ = extract_trade_details(trimmed, db)

        return bool((bool(your_fruits) != bool(their_fruits)))

    except:
        return False