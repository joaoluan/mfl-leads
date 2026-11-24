"""Telefone sempre em E.164: é a chave de dedupe entre fontes e do deep link."""

import phonenumbers


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
