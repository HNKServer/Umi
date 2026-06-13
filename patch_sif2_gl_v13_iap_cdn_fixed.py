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

OLD_PACKAGE = b'com.bushiroad.global.lovelive.sif2.google'
NEW_PACKAGE = b'com.bushiroad.global.lovelive.sif2.cdnfix'  # same length
OLD_PACKAGE_U16 = 'com.bushiroad.global.lovelive.sif2.google'.encode('utf-16le')
NEW_PACKAGE_U16 = 'com.bushiroad.global.lovelive.sif2.cdnfix'.encode('utf-16le')
OLD_GGL = b'http://localhost:8080'
NEW_GGL = b'http://127.1.1.1:8080'  # same length, loopback on Android
OLD_LOCAL_API = b'\x11\x00\x00\x00http://localhost/'
NEW_LOCAL_API = b'\x11\x00\x00\x00http://127.0.0.1/'
OLD_LOCAL_ASSET = b'\x18\x00\x00\x00http://localhost/assets/'
NEW_LOCAL_ASSET = b'\x16\x00\x00\x00http://127.1.1.1:8080/\x00\x00'

DEX_PATCHES = {
    0x62D15E: bytes.fromhex('29 00 20 00'),
    0x62D52E: bytes.fromhex('29 00 20 00'),
    0x60293C: bytes.fromhex('0E 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00'),
    0x4081D4: bytes.fromhex('0E 00 00 00 00 00 00 00'),
    0x4082EC: bytes.fromhex('0E 00 00 00 00 00 00 00'),
}
DEX_EXPECTED = {
    0x62D15E: [bytes.fromhex('38 02 20 00'), bytes.fromhex('29 00 20 00')],
    0x62D52E: [bytes.fromhex('38 02 20 00'), bytes.fromhex('29 00 20 00')],
    0x60293C: [bytes.fromhex('6E 10 B6 B6 02 00 0C 02 72 20 B3 B6 20 00 0E 00'), bytes.fromhex('0E 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00')],
    0x4081D4: [bytes.fromhex('6E 10 CE 32 07 00 0A 00'), bytes.fromhex('0E 00 00 00 00 00 00 00')],
    0x4082EC: [bytes.fromhex('6E 10 CE 32 0C 00 0A 00'), bytes.fromhex('0E 00 00 00 00 00 00 00')],
}
RET_ZERO = bytes.fromhex('E0 03 1F AA C0 03 5F D6')
RET_FALSE = bytes.fromhex('00 00 80 52 C0 03 5F D6')
IL2CPP_PATCHES = {
    0x3A1B578: RET_ZERO, 0x3A1B660: RET_ZERO, 0x3A1B6EC: RET_ZERO, 0x3A1B79C: RET_ZERO,
    0x3A1B7A4: RET_ZERO, 0x3A1B9E4: RET_ZERO, 0x3A1BAE8: RET_ZERO, 0x3A1D1CC: RET_ZERO,
    0x379888C: RET_FALSE, 0x3798BFC: RET_ZERO, 0x3798DB8: RET_ZERO,
    0x2B0DD94: RET_ZERO, 0x2B0E190: RET_ZERO, 0x2B0DBFC: RET_ZERO, 0x2B101A0: RET_ZERO,
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

def patch_fixed(data: bytes, name: str) -> bytes:
    # Do not blindly rewrite Unity serialized asset files. Even same-length
    # replacements can invalidate serialized resource metadata and cause
    # "Unknown error occurred while loading sharedassets*.assets" on startup.
    unity_data = name.startswith('assets/bin/Data/') or name.startswith('assets/BuildAssets/')
    if not unity_data:
        data = data.replace(OLD_PACKAGE, NEW_PACKAGE).replace(OLD_PACKAGE_U16, NEW_PACKAGE_U16)
    if name == 'assets/ggl_url.txt':
        data = data.replace(OLD_GGL, NEW_GGL)
    if name == 'assets/bin/Data/sharedassets10.assets.split1':
        before_len = len(data)
        data = data.replace(OLD_LOCAL_API, NEW_LOCAL_API)
        if OLD_LOCAL_ASSET in data:
            data = data.replace(OLD_LOCAL_ASSET, NEW_LOCAL_ASSET)
        elif NEW_LOCAL_ASSET not in data:
            raise RuntimeError('Local asset CDN string not found')
        if len(data) != before_len:
            raise RuntimeError(f'sharedassets10 split1 size changed: {before_len} -> {len(data)}')
    return data

def patch_dex(data: bytes) -> bytes:
    b = bytearray(data)
    for off, allowed in DEX_EXPECTED.items():
        patch = DEX_PATCHES[off]
        actual = bytes(b[off:off+len(patch)])
        if actual not in allowed:
            raise RuntimeError(f'classes.dex offset 0x{off:X} mismatch: got {actual.hex()}')
    for off, patch in DEX_PATCHES.items():
        b[off:off+len(patch)] = patch
    return fix_dex_header(patch_fixed(bytes(b), 'classes.dex'))

def patch_il2cpp(data: bytes) -> bytes:
    b = bytearray(data)
    for off, allowed in IL2CPP_EXPECTED.items():
        patch = IL2CPP_PATCHES[off]
        actual = bytes(b[off:off+len(patch)])
        if actual not in allowed:
            raise RuntimeError(f'libil2cpp.so offset 0x{off:X} mismatch: got {actual.hex()}')
    for off, patch in IL2CPP_PATCHES.items():
        b[off:off+len(patch)] = patch
    return patch_fixed(bytes(b), 'lib/arm64-v8a/libil2cpp.so')

def pad_extra_for_alignment(current_offset, filename, extra, align=4):
    # local data offset = current + 30 + len(filename) + len(extra)
    base = current_offset + 30 + len(filename.encode('utf-8')) + len(extra)
    need = (-base) % align
    if need == 0: return extra
    # valid extra field header 0xCAFE + size
    if need < 4:
        need += align
    payload = b'\0' * (need - 4)
    return extra + struct.pack('<HH', 0xCAFE, len(payload)) + payload

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
            elif name == 'classes.dex':
                data = patch_dex(data)
            elif name == 'lib/arm64-v8a/libil2cpp.so':
                data = patch_il2cpp(data)
            else:
                data = patch_fixed(data, name)
            out_info = zipfile.ZipInfo(filename=name, date_time=info.date_time)
            out_info.compress_type = zipfile.ZIP_STORED if name == 'resources.arsc' else info.compress_type
            out_info.external_attr = info.external_attr
            out_info.comment = info.comment
            out_info.extra = info.extra
            out_info.internal_attr = info.internal_attr
            if name == 'resources.arsc':
                out_info.extra = pad_extra_for_alignment(zout.fp.tell(), name, out_info.extra, 4)
            zout.writestr(out_info, data)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('input_apk')
    ap.add_argument('output_unsigned_apk')
    args = ap.parse_args()
    repack_apk(Path(args.input_apk), Path(args.output_unsigned_apk))
    out=Path(args.output_unsigned_apk)
    print('[ok unsigned]', out)
    print('[sha256 unsigned]', hashlib.sha256(out.read_bytes()).hexdigest())

if __name__ == '__main__': main()

# V13 NOTE:
# The previous v11 package used a malformed custom APK Signature Scheme v2 block:
# its V2 value missed the required outer length-prefixed signers sequence, so
# Android reported "No supported signatures found". The distributed v12 APK was
# rebuilt with the corrected signer structure:
#   V2 value = length_prefix(sequence_of_length_prefixed_signers)
# rather than just sequence_of_length_prefixed_signers.
#
# This script intentionally produces an unsigned APK by default. Sign it with
# the official Android SDK apksigner when building locally, e.g.:
#   python patch_sif2_gl_v13_iap_cdn_fixed.py input.apk unsigned.apk
#   apksigner sign --ks your.jks --out signed.apk unsigned.apk

# V13 fixes the v12 startup popup/black-background issue by preserving the
# byte size and serialized layout of assets/bin/Data/sharedassets10.assets.split1
# and by avoiding global package-name replacements inside Unity asset files.
