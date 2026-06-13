#!/usr/bin/env python3
import argparse, hashlib, struct, zipfile, zlib
from pathlib import Path

UNITY_SERVICES_PATCH = (
    '{"Keys":["com.unity.services.core.cloud-environment",'
    '"com.unity.services.core.version",'
    '"com.unity.services.core.initializer-assembly-qualified-names",'
    '"com.unity.services.core.all-package-names"],'
    '"Values":[{"m_Value":"production","m_IsReadOnly":false},'
    '{"m_Value":"1.8.2","m_IsReadOnly":true},'
    '{"m_Value":"Unity.Services.Core.Registration.CorePackageInitializer, Unity.Services.Core.Registration, Version=0.0.0.0, Culture=neutral, PublicKeyToken=null","m_IsReadOnly":true},'
    '{"m_Value":"com.unity.services.core","m_IsReadOnly":false}]}'
).encode('utf-8')

# v10: do NOT touch DEX string_data/string_ids.
# New idea: stop Play Billing queries at the BillingClientImpl entry points.
# If querySkuDetailsAsync/queryProductDetailsAsync return immediately, Play Store never returns
# response code 3, so Unity IAP should not receive NoProductsAvailable from BillingClient.
DEX_PATCHES = {
    # GREE billing callback branch fixes retained from older safe builds.
    0x62D15E: bytes.fromhex('29 00 20 00'),
    0x62D52E: bytes.fromhex('29 00 20 00'),

    # UnityPurchasing.OnSetupFailed: after loading callback field, return-void and NOP rest.
    0x60293C: bytes.fromhex('0E 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00'),

    # com.android.billingclient.api.BillingClientImpl.queryProductDetailsAsync(...): return-void at entry.
    0x4081D4: bytes.fromhex('0E 00 00 00 00 00 00 00'),
    # com.android.billingclient.api.BillingClientImpl.querySkuDetailsAsync(...): return-void at entry.
    0x4082EC: bytes.fromhex('0E 00 00 00 00 00 00 00'),
}
DEX_EXPECTED = {
    0x62D15E: [bytes.fromhex('38 02 20 00'), bytes.fromhex('29 00 20 00')],
    0x62D52E: [bytes.fromhex('38 02 20 00'), bytes.fromhex('29 00 20 00')],
    0x60293C: [
        bytes.fromhex('6E 10 B6 B6 02 00 0C 02 72 20 B3 B6 20 00 0E 00'),
        bytes.fromhex('0E 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00'),
    ],
    0x4081D4: [
        bytes.fromhex('6E 10 CE 32 07 00 0A 00'),
        bytes.fromhex('0E 00 00 00 00 00 00 00'),
    ],
    0x4082EC: [
        bytes.fromhex('6E 10 CE 32 0C 00 0A 00'),
        bytes.fromhex('0E 00 00 00 00 00 00 00'),
    ],
}

RET_ZERO = bytes.fromhex('E0 03 1F AA C0 03 5F D6')
RET_FALSE = bytes.fromhex('00 00 80 52 C0 03 5F D6')

IL2CPP_PATCHES = {
    # Sonet.IAPController / debug helpers.
    0x3A1B578: RET_ZERO,
    0x3A1B660: RET_ZERO,
    0x3A1B6EC: RET_ZERO,
    0x3A1B79C: RET_ZERO,
    0x3A1B7A4: RET_ZERO,
    0x3A1B9E4: RET_ZERO,
    0x3A1BAE8: RET_ZERO,
    0x3A1D1CC: RET_ZERO,

    # Shock.MngGGLData payment toggles.
    0x379888C: RET_FALSE,
    0x3798BFC: RET_ZERO,
    0x3798DB8: RET_ZERO,

    # Protocol-side fatal/error handlers.
    0x2B0DD94: RET_ZERO,
    0x2B0E190: RET_ZERO,
    0x2B0DBFC: RET_ZERO,
    0x2B101A0: RET_ZERO,
}
IL2CPP_EXPECTED = {
    0x3A1B578: [bytes.fromhex('00 08 40 F9 E1 03 1F AA'), RET_ZERO],
    0x3A1B660: [bytes.fromhex('F4 0F 1E F8 F3 7B 01 A9'), RET_ZERO],
    0x3A1B6EC: [bytes.fromhex('F7 5B BD A9 F5 53 01 A9'), RET_ZERO],
    0x3A1B79C: [bytes.fromhex('E1 03 1F AA E7 B4 F2 17'), RET_ZERO],
    0x3A1B7A4: [bytes.fromhex('F7 5B BD A9 F5 53 01 A9'), RET_ZERO],
    0x3A1B9E4: [bytes.fromhex('F7 5B BD A9 F5 53 01 A9'), RET_ZERO],
    0x3A1BAE8: [bytes.fromhex('E1 03 1F AA 14 B4 F2 17'), RET_ZERO],
    0x3A1D1CC: [bytes.fromhex('F8 0F 1C F8 F7 5B 01 A9'), RET_ZERO],
    0x379888C: [bytes.fromhex('F5 53 BE A9 F3 7B 01 A9'), RET_FALSE],
    0x3798BFC: [bytes.fromhex('F5 53 BE A9 F3 7B 01 A9'), RET_ZERO],
    0x3798DB8: [bytes.fromhex('E1 03 1F AA 60 BF FC 17'), RET_ZERO],
    0x2B0DD94: [bytes.fromhex('FF 83 01 D1 F8 13 00 F9'), RET_ZERO],
    0x2B0E190: [bytes.fromhex('FF C3 00 D1 FE 13 00 F9'), RET_ZERO],
    0x2B0DBFC: [bytes.fromhex('FE 0F 1F F8 80 01 00 B4'), RET_ZERO],
    0x2B101A0: [bytes.fromhex('F3 7B BF A9 E0 03 1F AA'), RET_ZERO],
}

def fix_dex_header(data: bytes) -> bytes:
    b = bytearray(data)
    b[12:32] = hashlib.sha1(b[32:]).digest()
    b[8:12] = struct.pack('<I', zlib.adler32(b[12:]) & 0xffffffff)
    return bytes(b)

def patch_dex(data: bytes) -> bytes:
    b = bytearray(data)
    for off, allowed in DEX_EXPECTED.items():
        patch = DEX_PATCHES[off]
        actual = bytes(b[off:off+len(patch)])
        if actual not in allowed:
            raise RuntimeError(f'classes.dex offset 0x{off:X} mismatch: got {actual.hex()}, allowed {[x.hex() for x in allowed]}')
    for off, patch in DEX_PATCHES.items():
        b[off:off+len(patch)] = patch
        print(f'[patch] classes.dex 0x{off:X}: {patch.hex()}')
    return fix_dex_header(bytes(b))

def patch_il2cpp(data: bytes) -> bytes:
    b = bytearray(data)
    for off, allowed in IL2CPP_EXPECTED.items():
        patch = IL2CPP_PATCHES[off]
        actual = bytes(b[off:off+len(patch)])
        if actual not in allowed:
            raise RuntimeError(f'libil2cpp.so offset 0x{off:X} mismatch: got {actual.hex()}, allowed {[x.hex() for x in allowed]}')
    for off, patch in IL2CPP_PATCHES.items():
        b[off:off+len(patch)] = patch
        print(f'[patch] libil2cpp.so 0x{off:X}: {patch.hex()}')
    return bytes(b)

def repack_apk(input_apk: Path, out_unsigned: Path):
    if out_unsigned.exists(): out_unsigned.unlink()
    with zipfile.ZipFile(input_apk, 'r') as zin, zipfile.ZipFile(out_unsigned, 'w', allowZip64=True) as zout:
        for info in zin.infolist():
            name = info.filename
            if name.startswith('META-INF/'):
                continue
            data = zin.read(name)
            if name == 'assets/UnityServicesProjectConfiguration.json':
                data = UNITY_SERVICES_PATCH
                print('[patch] removed com.unity.purchasing from UnityServicesProjectConfiguration.json')
            elif name == 'classes.dex':
                data = patch_dex(data)
                print('[patch] patched classes.dex: safe billing no-callback v10')
            elif name == 'lib/arm64-v8a/libil2cpp.so':
                data = patch_il2cpp(data)
                print('[patch] patched libil2cpp.so IAP/protocol paths')
            out_info = zipfile.ZipInfo(filename=name, date_time=info.date_time)
            out_info.compress_type = info.compress_type
            out_info.external_attr = info.external_attr
            out_info.comment = info.comment
            out_info.extra = info.extra
            out_info.internal_attr = info.internal_attr
            zout.writestr(out_info, data)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('input_apk')
    ap.add_argument('output_unsigned_apk')
    args = ap.parse_args()
    repack_apk(Path(args.input_apk), Path(args.output_unsigned_apk))
    out = Path(args.output_unsigned_apk)
    print('[ok unsigned]', out)
    print('[sha256 unsigned]', hashlib.sha256(out.read_bytes()).hexdigest())

if __name__ == '__main__':
    main()
