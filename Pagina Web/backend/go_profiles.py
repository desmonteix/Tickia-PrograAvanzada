"""Owner-bound payout identities. Provider KYC, not a user checkbox, authorizes payouts."""
import hashlib
import json
from datetime import datetime, timezone

from . import models
from .go_fees import fee_terms
from .payment_provider import PaymentUnavailable, PaymentDeclined, PaymentUncertain

STATUSES = {'PENDING', 'PROCESSING', 'VERIFIED', 'REJECTED', 'EXPIRED', 'BLOCKED'}


def identity_hash(data):
    return hashlib.sha256(':'.join(str(data.get(x, '')) for x in
                                   ('country', 'document_type', 'document')).encode()).hexdigest()


def account_hash(data):
    return hashlib.sha256(':'.join(str(data.get(x, '')) for x in
        ('country', 'currency', 'bank_code', 'bank_account', 'account_type')).encode()).hexdigest()


def apply_beneficiary(profile, data, owner_email):
    if (not isinstance(data, dict) or identity_hash(data) != profile.identity_hash
            or data.get('email', '').casefold() != owner_email.casefold()
            or data.get('flow_type') != 'B2C' or data.get('status') not in STATUSES):
        raise PaymentUncertain('La identidad bancaria no coincide con el perfil de Tickia.')
    accounts = data.get('bank_accounts')
    if not isinstance(accounts, list):
        raise PaymentUncertain('La pasarela no confirmó la cuenta bancaria.')
    matching = [x for x in accounts if isinstance(x, dict) and account_hash(x) == profile.account_hash]
    if len(matching) != 1 or type(matching[0].get('id')) is not int or matching[0]['id'] <= 0:
        raise PaymentUncertain('La cuenta bancaria requiere revisión.')
    beneficiary_id = str(data.get('id', ''))
    if not beneficiary_id.isdigit() or (profile.beneficiary_id and profile.beneficiary_id != beneficiary_id):
        raise PaymentUncertain('Beneficiario no válido.')
    if profile.bank_account_id and profile.bank_account_id != matching[0]['id']:
        raise PaymentUncertain('La cuenta bancaria cambió; requiere una nueva revisión.')
    profile.beneficiary_id = beneficiary_id
    profile.bank_account_id = matching[0]['id']
    profile.status = data['status']
    profile.error = None
    profile.request_encrypted = None
    profile.updated_at = datetime.now(timezone.utc)


def refresh_profile(db, profile, provider):
    user = db.get(models.User, profile.user_id)
    if profile.beneficiary_id:
        data = provider.retrieve_beneficiary(profile.beneficiary_id)
        apply_beneficiary(profile, data, user.email)
    else:
        # Registration has no documented idempotency. Recover, never re-POST.
        data = provider.list_beneficiaries()
        if not isinstance(data, list):
            raise PaymentUncertain('No se pudo conciliar el registro del beneficiario.')
        matches = [x for x in data if isinstance(x, dict) and identity_hash(x) == profile.identity_hash]
        if len(matches) != 1:
            raise PaymentUncertain('Registro pendiente de conciliación. No se enviará otro registro.')
        apply_beneficiary(profile, matches[0], user.email)
    db.commit()
    return profile


def profile_ready(profile, terms=None):
    terms = terms or fee_terms()
    return bool(profile and profile.status == 'VERIFIED' and profile.beneficiary_id
                and profile.bank_account_id and profile.fee_terms_hash == terms['hash'])


def profile_view(profile, provider, required=True, error=None):
    try:
        terms = fee_terms()
    except PaymentUnavailable:
        terms = None
    accepted = bool(profile and terms and profile.fee_terms_hash == terms['hash'])
    link = None
    if profile and profile.beneficiary_id and profile.status != 'VERIFIED' and not error:
        try:
            link = provider.validation_link(profile.beneficiary_id)
        except (PaymentUnavailable, PaymentDeclined, PaymentUncertain):
            error = 'No se pudo recuperar el enlace de verificación. Intenta consultar de nuevo.'
    return {'required': required, 'status': profile.status if profile else 'NOT_CONFIGURED',
            'bank_account_last4': profile.account_last4 if profile else None,
            'validation_url': link, 'fee_terms': terms, 'fee_terms_accepted': accepted,
            'can_sell': bool(not required or (terms and not error and profile_ready(profile, terms))),
            'error': error or (profile.error if profile else None)}
