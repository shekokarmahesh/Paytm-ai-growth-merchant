"""Stand-ins for Paytm merchant APIs (cashback campaigns, promo links). Deterministic ids, no network."""
import hashlib
from urllib.parse import quote


def create_cashback_campaign(merchant_id: str, discount_pct: float, starts_at: str, ends_at: str,
                             audience: list[str]) -> str:
    key = f"{merchant_id}|{discount_pct}|{starts_at}|{len(audience)}"
    return "PTMCB-" + hashlib.sha1(key.encode()).hexdigest()[:8].upper()


def voucher_code(campaign_id: str, payer_hash: str) -> str:
    return "VYP" + hashlib.sha1(f"{campaign_id}|{payer_hash}".encode()).hexdigest()[:6].upper()


def promo_upi_link(vpa: str, name: str, note: str) -> str:
    return f"upi://pay?pa={vpa}&pn={quote(name)}&tn={quote(note)}&cu=INR"
