# Copyright (c) 2020 Yubico AB
# All rights reserved.
#
#   Redistribution and use in source and binary forms, with or
#   without modification, are permitted provided that the following
#   conditions are met:
#
#    1. Redistributions of source code must retain the above copyright
#       notice, this list of conditions and the following disclaimer.
#    2. Redistributions in binary form must reproduce the above
#       copyright notice, this list of conditions and the following
#       disclaimer in the documentation and/or other materials provided
#       with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
# FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
# COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
# INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
# BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
# LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
# ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

from __future__ import absolute_import, unicode_literals

from .. import cbor
from ..ctap import CtapError

from enum import IntEnum, unique
import struct


class CredentialManagement(object):
    """Implementation of a draft specification of the Credential Management API.
    WARNING: This specification is not final and this class is likely to change.

    :param ctap: An instance of a CTAP2 object.
    :param pin_uv_protocol: An instance of a PinUvAuthProtocol.
    :param pin_uv_token: A valid PIN/UV Auth Token for the current CTAP session.
    """

    @unique
    class CMD(IntEnum):
        GET_CREDS_METADATA = 0x01
        ENUMERATE_RPS_BEGIN = 0x02
        ENUMERATE_RPS_NEXT = 0x03
        ENUMERATE_CREDS_BEGIN = 0x04
        ENUMERATE_CREDS_NEXT = 0x05
        DELETE_CREDENTIAL = 0x06

    @unique
    class PARAM(IntEnum):
        RP_ID_HASH = 0x01
        CREDENTIAL_ID = 0x02

    @unique
    class RESULT(IntEnum):
        EXISTING_CRED_COUNT = 0x01
        MAX_REMAINING_COUNT = 0x02
        RP = 0x03
        RP_ID_HASH = 0x04
        TOTAL_RPS = 0x05
        USER = 0x06
        CREDENTIAL_ID = 0x07
        PUBLIC_KEY = 0x08
        TOTAL_CREDENTIALS = 0x09
        CRED_PROTECT = 0x0A
        LARGE_BLOB_KEY = 0x0B

    def __init__(self, ctap, pin_uv_protocol, pin_uv_token):
        if not ctap.info.options.get("credMgmt"):
            # We also support the Prototype command
            if not ctap.info.options.get("credentialMgmtPreview"):
                raise ValueError("Authenticator does not support Credential Management")

        self.ctap = ctap
        self.pin_uv_protocol = pin_uv_protocol
        self.pin_uv_token = pin_uv_token

    def _call(self, sub_cmd, params=None, auth=True):
        kwargs = {"sub_cmd": sub_cmd, "sub_cmd_params": params}
        if auth:
            msg = struct.pack(">B", sub_cmd)
            if params is not None:
                msg += cbor.encode(params)
            kwargs["pin_uv_protocol"] = self.pin_uv_protocol.VERSION
            kwargs["pin_uv_param"] = self.pin_uv_protocol.authenticate(
                self.pin_uv_token, msg
            )
        return self.ctap.credential_mgmt(**kwargs)

    def get_metadata(self):
        """Get credentials metadata.

        This returns the existing resident credentials count, and the max
        possible number of remaining resident credentials (the actual number of
        remaining credentials may depend on algorithm choice, etc).

        :return: A dict containing EXISTING_CRED_COUNT, and MAX_REMAINING_COUNT.
        """
        return self._call(CredentialManagement.CMD.GET_CREDS_METADATA)

    def enumerate_rps_begin(self):
        """Start enumeration of RP entities of resident credentials.

        This will begin enumeration of stored RP entities, returning the first
        entity, as well as a count of the total number of entities stored.

        :return: A dict containing RP, RP_ID_HASH, and TOTAL_RPS.
        """
        return self._call(CredentialManagement.CMD.ENUMERATE_RPS_BEGIN)

    def enumerate_rps_next(self):
        """Get the next RP entity stored.

        This continues enumeration of stored RP entities, returning the next
        entity.

        :return: A dict containing RP, and RP_ID_HASH.
        """
        return self._call(CredentialManagement.CMD.ENUMERATE_RPS_NEXT, auth=False)

    def enumerate_rps(self):
        """Convenience method to enumerate all RPs.

        See enumerate_rps_begin and enumerate_rps_next for details.
        """
        first = self.enumerate_rps_begin()
        n_rps = first[CredentialManagement.RESULT.TOTAL_RPS]
        if n_rps == 0:
            return []
        rest = [self.enumerate_rps_next() for _ in range(1, n_rps)]
        return [first] + rest

    def enumerate_creds_begin(self, rp_id_hash):
        """Start enumeration of resident credentials.

        This will begin enumeration of resident credentials for a given RP,
        returning the first credential, as well as a count of the total number
        of resident credentials stored for the given RP.

        :param rp_id_hash: SHA256 hash of the RP ID.
        :return: A dict containing USER, CREDENTIAL_ID, PUBLIC_KEY, and
            TOTAL_CREDENTIALS.
        """
        return self._call(
            CredentialManagement.CMD.ENUMERATE_CREDS_BEGIN,
            {CredentialManagement.PARAM.RP_ID_HASH: rp_id_hash},
        )

    def enumerate_creds_next(self):
        """Get the next resident credential stored.

        This continues enumeration of resident credentials, returning the next
        credential.

        :return: A dict containing USER, CREDENTIAL_ID, and PUBLIC_KEY.
        """
        return self._call(CredentialManagement.CMD.ENUMERATE_CREDS_NEXT, auth=False)

    def enumerate_creds(self, *args, **kwargs):
        """Convenience method to enumerate all resident credentials for an RP.

        See enumerate_creds_begin and enumerate_creds_next for details.
        """
        try:
            first = self.enumerate_creds_begin(*args, **kwargs)
        except CtapError as e:
            if e.code == CtapError.ERR.NO_CREDENTIALS:
                return []
            raise  # Other error
        rest = [
            self.enumerate_creds_next()
            for _ in range(
                1, first.get(CredentialManagement.RESULT.TOTAL_CREDENTIALS, 1)
            )
        ]
        return [first] + rest

    def delete_cred(self, cred_id):
        """Delete a resident credential.

        :param cred_id: The ID of the credential to delete.
        """
        return self._call(
            CredentialManagement.CMD.DELETE_CREDENTIAL,
            {CredentialManagement.PARAM.CREDENTIAL_ID: cred_id},
        )
