"""Telefone sempre em E.164: é a chave de dedupe entre fontes e do deep link."""

import phonenumbers


def para_e164(bruto: str) -> str | None:
    """None quando inválido: o lead vai para `enriquecimento` em vez de receber mensagem errada."""
    try:
        numero = phonenumbers.parse(bruto, "BR")
    except phonenumbers.NumberParseException:
        return None
    if not phonenumbers.is_valid_number(numero):
        return None
    return phonenumbers.format_number(numero, phonenumbers.PhoneNumberFormat.E164)
