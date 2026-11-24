"""Telefone sempre em E.164: é a chave de dedupe entre fontes e do deep link."""

import re

import phonenumbers

# Link de conversa com número: wa.me/<n>, wa.me/c/<n> (catálogo) e api.whatsapp.com/send?phone=<n>.
WHATSAPP = re.compile(r"(?:wa\.me/(?:c/)?|whatsapp\.com/send/?\?(?:[^\s\"'<>]*?&)?phone=)\+?(\d[\d.]{9,15})")


def para_e164(bruto: str) -> str | None:
    """None quando inválido: o lead vai para `enriquecimento` em vez de receber mensagem errada.

    Celular antigo sem o nono dígito (comum em JID do WhatsApp) ganha o 9 para casar com as outras fontes.
    """
    try:
        numero = phonenumbers.parse(bruto, "BR")
    except phonenumbers.NumberParseException:
        return None
    if not phonenumbers.is_valid_number(numero) and numero.country_code == 55:
        nacional = str(numero.national_number)
        if len(nacional) == 10 and nacional[2] in "6789":
            numero = phonenumbers.parse(f"+55{nacional[:2]}9{nacional[2:]}")
    if not phonenumbers.is_valid_number(numero):
        return None
    return phonenumbers.format_number(numero, phonenumbers.PhoneNumberFormat.E164)


def de_jid(jid: str) -> str | None:
    """Só JID de telefone vira número; LID (@lid) não é telefone e grupo não é pessoa."""
    usuario, _, dominio = (jid or "").partition("@")
    return para_e164("+" + usuario) if dominio == "s.whatsapp.net" and usuario.isdigit() else None


def celular(e164: str | None) -> bool:
    return bool(e164) and phonenumbers.number_type(phonenumbers.parse(e164)) == phonenumbers.PhoneNumberType.MOBILE


def whatsapp_em(texto: str) -> str | None:
    """Número de um link de WhatsApp: confirmado como WhatsApp mesmo sendo fixo (WhatsApp Business)."""
    for bruto in WHATSAPP.findall(texto or ""):
        digitos = bruto.replace(".", "")
        tel = para_e164("+" + digitos if len(digitos) >= 12 else digitos)
        if tel:
            return tel
    return None
