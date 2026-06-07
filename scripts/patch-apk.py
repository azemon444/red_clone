#!/usr/bin/env python3
"""
Patch Santander APK for offline clone use:
  - Redirect API to local mock server
  - Disable SSL certificate pinning
  - Change package name
  - Enable cleartext HTTP
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
APKTOOL_SRC = ROOT / "apktool"
PATCHED_DIR = ROOT / "patched-app"
OUTPUT_APK = ROOT / "SantanderClone.apk"

OLD_PACKAGE = "pt.santander.oneappparticulares"
NEW_PACKAGE = "com.azemon.santanderclone"
OLD_PACKAGE_PATH = OLD_PACKAGE.replace(".", "/")
NEW_PACKAGE_PATH = NEW_PACKAGE.replace(".", "/")

# Default: emulator loopback. Override with MOCK_HOST env or --mock-host for cloud deploy.
DEFAULT_MOCK_HOST = "http://10.0.2.2:9090"


def build_url_replacements(mock_host: str) -> list:
    host = mock_host.rstrip("/")
    parsed = urlparse(host)
    hostname = parsed.hostname or "10.0.2.2"
    return [
        ("https://api-eeic.apis.santander.pt/santander/eeic/", f"{host}/santander/eeic/"),
        ("https://api-eeic.apis.santander.pt/santander/eeic", f"{host}/santander/eeic"),
        ("https://api-eeic9.apis.santander.pt/santander/eeic/", f"{host}/santander/eeic/"),
        ("https://api-eeic9.apis.santander.pt/santander/eeic", f"{host}/santander/eeic"),
        ("api-eeic.apis.santander.pt", hostname),
        ("api-eeic9.apis.santander.pt", hostname),
        ("https://pfm.santander.pt", host),
        ("https://subscriptions.santander.pt", host),
        ("https://micrositeoneapp.santander.pt", f"{host}/microsite"),
        ("https://micrositeoneapp9.santander.pt", f"{host}/microsite"),
        ("https://poupareinvestir.santander.pt", f"{host}/demo"),
        ("https://www.particulares.santander.pt", f"{host}/demo"),
        ("https://www.santander.pt", f"{host}/demo"),
        ("https://carbonfootprint.eu.gruposantander.com", f"{host}/demo"),
        ("https://configsantander.plexus.services", f"{host}/microsite"),
    ]


URL_REPLACEMENTS = build_url_replacements(DEFAULT_MOCK_HOST)


def run(cmd, cwd=None):
    print(f"  $ {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
        raise RuntimeError(f"Command failed: {' '.join(cmd)}")
    return result.stdout


def copy_apktool_tree():
    if PATCHED_DIR.exists():
        shutil.rmtree(PATCHED_DIR)
    print(f"Copying {APKTOOL_SRC} -> {PATCHED_DIR}")
    shutil.copytree(APKTOOL_SRC, PATCHED_DIR)


def replace_in_file(path: Path, replacements: list):
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return
    original = text
    for old, new in replacements:
        text = text.replace(old, new)
    if text != original:
        path.write_text(text, encoding="utf-8")


def patch_all_files():
    print("Patching URLs and package references...")
    pkg_replacements = [
        (OLD_PACKAGE, NEW_PACKAGE),
        (OLD_PACKAGE_PATH, NEW_PACKAGE_PATH),
        (f"L{OLD_PACKAGE_PATH}", f"L{NEW_PACKAGE_PATH}"),
    ]
    all_replacements = URL_REPLACEMENTS + pkg_replacements

    extensions = {".smali", ".xml", ".json", ".properties", ".txt", ".html", ".js"}
    count = 0
    for root, _, files in os.walk(PATCHED_DIR):
        for name in files:
            if Path(name).suffix in extensions or name == "AndroidManifest.xml":
                p = Path(root) / name
                before = p.read_text(encoding="utf-8", errors="ignore") if p.exists() else ""
                replace_in_file(p, all_replacements)
                after = p.read_text(encoding="utf-8", errors="ignore") if p.exists() else ""
                if before != after:
                    count += 1
    print(f"  Modified {count} files")


def patch_manifest():
    manifest = PATCHED_DIR / "AndroidManifest.xml"
    text = manifest.read_text(encoding="utf-8")
    text = text.replace(f'package="{OLD_PACKAGE}"', f'package="{NEW_PACKAGE}"')
    text = text.replace('android:label="Santander"', 'android:label="Banco Clone"')
    text = text.replace(
        'android:usesCleartextTraffic="@string/cleartext_traffic"',
        'android:usesCleartextTraffic="true"',
    )
    text = re.sub(
        rf'android:authorities="{re.escape(OLD_PACKAGE)}',
        f'android:authorities="{NEW_PACKAGE}',
        text,
    )
    # Original Play Store bundle — strip split requirements so a single APK installs
    text = re.sub(r'\s*android:requiredSplitTypes="[^"]*"', "", text)
    text = re.sub(r'\s*android:splitTypes="[^"]*"', "", text)
    text = re.sub(
        r'\s*<meta-data android:name="com\.android\.vending\.splits\.required"[^/]*/>\n?',
        "",
        text,
    )
    text = re.sub(
        r'\s*<meta-data android:name="com\.android\.vending\.splits"[^/]*/>\n?',
        "",
        text,
    )
    text = re.sub(
        r'\s*<meta-data android:name="com\.android\.vending\.derived\.apk\.id"[^/]*/>\n?',
        "",
        text,
    )
    text = text.replace(
        'android:resource="@null"',
        'android:resource="@mipmap/ic_launcher"',
    )
    text = text.replace(
        'android:extractNativeLibs="false"',
        'android:extractNativeLibs="true"',
    )
    manifest.write_text(text, encoding="utf-8")
    print("Patched AndroidManifest.xml")


def patch_smali_method(path: Path, method_signature: str, new_body: str) -> bool:
    """Replace a single .method ... .end method block in a smali file."""
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8")
    pattern = rf"\.method {re.escape(method_signature)}.*?\.end method"
    new_text, n = re.subn(pattern, new_body, text, count=1, flags=re.DOTALL)
    if n:
        path.write_text(new_text, encoding="utf-8")
        return True
    return False


def patch_pairip_bypass():
    """Bypass PairIP native protection (libpairipcore.so lives in split APKs)."""
    print("Patching PairIP protection bypass...")

    core_factory = PATCHED_DIR / "smali_classes2" / "androidx" / "core" / "app" / "CoreComponentFactory.smali"
    patch_smali_method(
        core_factory,
        "static constructor <clinit>()V",
        """.method static constructor <clinit>()V
    .locals 0

    return-void
.end method""",
    )

    vm_runner = PATCHED_DIR / "smali_classes2" / "com" / "pairip" / "VMRunner.smali"
    patch_smali_method(
        vm_runner,
        "static constructor <clinit>()V",
        """.method static constructor <clinit>()V
    .locals 0

    return-void
.end method""",
    )
    patch_smali_method(
        vm_runner,
        "public static invoke(Ljava/lang/String;[Ljava/lang/Object;)Ljava/lang/Object;",
        """.method public static invoke(Ljava/lang/String;[Ljava/lang/Object;)Ljava/lang/Object;
    .locals 1

    const/4 v0, 0x0

    return-object v0
.end method""",
    )

    signature_check = PATCHED_DIR / "smali_classes2" / "com" / "pairip" / "SignatureCheck.smali"
    patch_smali_method(
        signature_check,
        "public static verifyIntegrity(Landroid/content/Context;)V",
        """.method public static verifyIntegrity(Landroid/content/Context;)V
    .locals 0

    return-void
.end method""",
    )

    license_client = PATCHED_DIR / "smali_classes2" / "com" / "pairip" / "licensecheck" / "LicenseClient.smali"
    patch_smali_method(
        license_client,
        "public initializeLicenseCheck()V",
        """.method public initializeLicenseCheck()V
    .locals 1

    sget-object v0, Lcom/pairip/licensecheck/LicenseClient$LicenseCheckState;->FULL_CHECK_OK:Lcom/pairip/licensecheck/LicenseClient$LicenseCheckState;

    sput-object v0, Lcom/pairip/licensecheck/LicenseClient;->licenseCheckState:Lcom/pairip/licensecheck/LicenseClient$LicenseCheckState;

    return-void
.end method""",
    )

    manifest = PATCHED_DIR / "AndroidManifest.xml"
    text = manifest.read_text(encoding="utf-8")
    text = text.replace(
        'android:name="com.pairip.application.Application"',
        'android:name="com.santander.one.pt.app.AndroidApplication"',
    )
    manifest.write_text(text, encoding="utf-8")
    print("  PairIP bypass applied")


def patch_vm_reflection_bypass():
    """Replace PairIP null Method.invoke stubs with direct synthetic calls."""
    print("Patching VM reflection guards...")

    android_app = (
        PATCHED_DIR / "smali_classes11" / "com" / "santander" / "one" / "pt" / "app" / "AndroidApplication.smali"
    )
    patch_smali_method(
        android_app,
        "public onCreate()V",
        """.method public onCreate()V
    .locals 0

    invoke-super {p0}, Landroid/app/Application;->onCreate()V

    invoke-virtual {p0}, Lcom/santander/one/pt/app/AndroidApplication;->I()V

    invoke-virtual {p0}, Lcom/santander/one/pt/app/AndroidApplication;->w()V

    invoke-virtual {p0}, Lcom/santander/one/pt/app/AndroidApplication;->x()V

    invoke-virtual {p0}, Lcom/santander/one/pt/app/AndroidApplication;->G()V

    invoke-virtual {p0}, Lcom/santander/one/pt/app/AndroidApplication;->y()V

    return-void
.end method""",
    )

    public_activity = (
        PATCHED_DIR
        / "smali_classes3"
        / "es.2"
        / "bancosantander"
        / "apps"
        / "mobile"
        / "android"
        / "activities"
        / "PublicActivity.smali"
    )
    patch_smali_method(
        public_activity,
        "public onDestroy()V",
        """.method public onDestroy()V
    .locals 0

    invoke-static {p0}, Les/bancosantander/apps/mobile/android/activities/PublicActivity;->onDestroy$001(LAR/b;)V

    return-void
.end method""",
    )

    patched = 2
    reflection_block = re.compile(
        r"(\.method (?P<header>(?:public |protected |private )?\S+ (?P<name>\w+)\([^\)]*\)\S+)\s*\n"
        r"(?P<prologue>(?:\s+\.locals \d+\s*\n)?)"
        r"(?P<body>.*?"
        r"sget-object \w+, L[^;]+;->\w+:Ljava/lang/reflect/Method;\s*\n"
        r".*?"
        r"invoke-virtual \{.*?\}, Ljava/lang/reflect/Method;->invoke\(Ljava/lang/Object;\[Ljava/lang/Object;\)Ljava/lang/Object;\s*\n"
        r".*?)"
        r"\.end method)",
        re.DOTALL,
    )

    skip = {android_app, public_activity}
    for smali in PATCHED_DIR.rglob("*.smali"):
        if smali in skip:
            continue
        text = smali.read_text(encoding="utf-8")
        original = text

        for match in reflection_block.finditer(text):
            method_name = match.group("name")
            synthetic = re.search(
                rf"\.method public static synthetic {re.escape(method_name)}\$\d+",
                text,
            )
            if not synthetic:
                continue
            syn_match = re.search(
                rf"\.method public static synthetic ({re.escape(method_name)}\$\d+)\(([^)]*)\)(\S+)",
                text[synthetic.start() :],
            )
            if not syn_match:
                continue
            syn_name, syn_args, syn_ret = syn_match.groups()
            class_match = re.search(r"^\.class \S+ (L[^;]+;)", text, re.MULTILINE)
            if not class_match:
                continue
            class_desc = class_match.group(1)

            param_count = syn_args.count(";") if syn_args else 0
            if param_count == 0:
                regs = ""
            else:
                regs = ", ".join(f"p{i}" for i in range(param_count))
            invoke_line = (
                f"    invoke-static {{{regs}}}, {class_desc}->{syn_name}({syn_args}){syn_ret}\n"
            )

            new_method = (
                f".method {match.group('header')}\n"
                f"{match.group('prologue')}"
                f"{invoke_line}"
                f"    return-void\n"
                f".end method"
            )
            text = text.replace(match.group(0), new_method, 1)
            patched += 1

        if text != original:
            smali.write_text(text, encoding="utf-8")

    print(f"  VM reflection guards patched ({patched} methods)")


def patch_pairip_string_defaults():
    """Initialize PairIP obfuscated string holder fields to avoid NPE at class load."""
    print("Patching PairIP string defaults...")
    holder = PATCHED_DIR / "smali_classes2" / "vc" / "Cx" / "nSsMTQlTZZUS.smali"
    if not holder.exists():
        return
    text = holder.read_text(encoding="utf-8")
    if "<clinit>" in text:
        print("  PairIP string holder already patched")
        return
    fields = re.findall(r"\.field public static (\w+):Ljava/lang/String;", text)
    if not fields:
        return
    lines = [".method static constructor <clinit>()V", "    .locals 1", ""]
    for name in fields:
        lines.append('    const-string v0, ""')
        lines.append(f"    sput-object v0, Lvc/Cx/nSsMTQlTZZUS;->{name}:Ljava/lang/String;")
        lines.append("")
    lines.append("    return-void")
    lines.append(".end method")
    text = text.rstrip() + "\n\n\n# direct methods\n" + "\n".join(lines) + "\n"
    holder.write_text(text, encoding="utf-8")
    # Fix l1/b WRAP_DIMENSION constant used by ConstraintLayout
    l1_b = PATCHED_DIR / "smali_classes2" / "l1" / "b.smali"
    if l1_b.exists():
        l1_text = l1_b.read_text(encoding="utf-8")
        l1_text = l1_text.replace(
            "    const/4 v1, 0x0\n\n"
            "    sget-object v1, Lvc/Cx/nSsMTQlTZZUS;->sHnAacKR:Ljava/lang/String;\n\n"
            "    invoke-direct {v0, v1}, Ljava/lang/String;-><init>(Ljava/lang/String;)V",
            '    const-string v1, "WRAP_DIMENSION"\n\n'
            "    invoke-direct {v0, v1}, Ljava/lang/String;-><init>(Ljava/lang/String;)V",
        )
        l1_b.write_text(l1_text, encoding="utf-8")
    print(f"  Initialized {len(fields)} PairIP string fields + WRAP_DIMENSION")


def patch_kotlin_builtin_strings():
    """Replace VM-guarded Kotlin builtin names in WT/h (StandardNames)."""
    wt_h = PATCHED_DIR / "smali_classes4" / "WT" / "h.smali"
    if not wt_h.exists():
        return
    text = wt_h.read_text(encoding="utf-8")
    replacements = [
        (
            "    sget-object v0, Lq2/RCrk/GeeKAbXKd;->ITYYlRiFvb:Ljava/lang/String;\n\n"
            "    invoke-static {v0}, LWT/i;->b(Ljava/lang/String;)LWT/b;",
            '    const-string v0, "Comparable"\n\n'
            "    invoke-static {v0}, LWT/i;->b(Ljava/lang/String;)LWT/b;",
        ),
        (
            "    sget-object v2, Lu3/aan/HiKReLihbCmCBQ;->oRDTx:Ljava/lang/String;\n\n"
            "    invoke-static {v2}, LWT/i;->c(Ljava/lang/String;)LWT/b;",
            '    const-string v2, "Collection"\n\n'
            "    invoke-static {v2}, LWT/i;->c(Ljava/lang/String;)LWT/b;",
        ),
    ]
    for old, new in replacements:
        text = text.replace(old, new)
    wt_h.write_text(text, encoding="utf-8")
    print("  Patched Kotlin StandardNames VM strings (Comparable, Collection)")


def patch_gms_preconditions():
    """Prevent GMS Background API thread crash from killing the app offline."""
    print("Patching GMS Preconditions...")
    pre = PATCHED_DIR / "smali_classes7" / "com" / "google" / "android" / "gms" / "common" / "internal" / "Preconditions.smali"
    if not pre.exists():
        return
    bypasses = [
        (
            "public static checkNotNull(Ljava/lang/Object;)Ljava/lang/Object;",
            """.method public static checkNotNull(Ljava/lang/Object;)Ljava/lang/Object;
    .locals 0
    .annotation system Ldalvik/annotation/Signature;
        value = {
            "<T:",
            "Ljava/lang/Object;",
            ">(TT;)TT;"
        }
    .end annotation

    return-object p0
.end method""",
        ),
        (
            "public static checkNotEmpty(Ljava/lang/String;)Ljava/lang/String;",
            """.method public static checkNotEmpty(Ljava/lang/String;)Ljava/lang/String;
    .locals 0

    return-object p0
.end method""",
        ),
        (
            "public static checkNotEmpty(Ljava/lang/String;Ljava/lang/Object;)Ljava/lang/String;",
            """.method public static checkNotEmpty(Ljava/lang/String;Ljava/lang/Object;)Ljava/lang/String;
    .locals 0

    return-object p0
.end method""",
        ),
        (
            "public static checkArgument(Z)V",
            """.method public static checkArgument(Z)V
    .locals 0

    return-void
.end method""",
        ),
        (
            "public static checkArgument(ZLjava/lang/Object;)V",
            """.method public static checkArgument(ZLjava/lang/Object;)V
    .locals 0

    return-void
.end method""",
        ),
    ]
    for signature, body in bypasses:
        patch_smali_method(pre, signature, body)
    print("  GMS Preconditions bypassed (checkNotNull, checkNotEmpty, checkArgument)")


def patch_gms_connection_tracker():
    """Skip GMS service bind when PairIP leaves Intent component/package empty."""
    print("Patching GMS ConnectionTracker...")
    tracker = (
        PATCHED_DIR
        / "smali_classes7"
        / "com"
        / "google"
        / "android"
        / "gms"
        / "common"
        / "stats"
        / "ConnectionTracker.smali"
    )
    if not tracker.exists():
        return
    text = tracker.read_text(encoding="utf-8")
    needle = (
        ".method private static final zze(Landroid/content/Context;Landroid/content/Intent;"
        "Landroid/content/ServiceConnection;ILjava/util/concurrent/Executor;)Z\n"
        "    .locals 1\n\n"
        "    if-nez p4, :cond_0\n\n"
        "    const/4 p4, 0x0\n\n"
        "    :cond_0\n"
    )
    replacement = (
        ".method private static final zze(Landroid/content/Context;Landroid/content/Intent;"
        "Landroid/content/ServiceConnection;ILjava/util/concurrent/Executor;)Z\n"
        "    .locals 1\n\n"
        "    invoke-virtual {p1}, Landroid/content/Intent;->getComponent()Landroid/content/ComponentName;\n\n"
        "    move-result-object v0\n\n"
        "    if-nez v0, :cond_skip\n\n"
        "    invoke-virtual {p1}, Landroid/content/Intent;->getPackage()Ljava/lang/String;\n\n"
        "    move-result-object v0\n\n"
        "    invoke-static {v0}, Landroid/text/TextUtils;->isEmpty(Ljava/lang/CharSequence;)Z\n\n"
        "    move-result v0\n\n"
        "    if-eqz v0, :cond_skip\n\n"
        "    const/4 p0, 0x0\n\n"
        "    return p0\n\n"
        "    :cond_skip\n"
        "    if-nez p4, :cond_0\n\n"
        "    const/4 p4, 0x0\n\n"
        "    :cond_0\n"
    )
    if needle not in text:
        print("  ConnectionTracker already patched or layout changed")
        return
    tracker.write_text(text.replace(needle, replacement), encoding="utf-8")
    print("  GMS ConnectionTracker empty-intent guard added")


def patch_default_english_language():
    """Force English as default app language and skip first-run language picker."""
    print("Patching default language to English...")

    pt_config = PATCHED_DIR / "smali_classes11" / "uu.1" / "a.smali"
    if pt_config.exists():
        text = pt_config.read_text(encoding="utf-8")
        text = text.replace(
            "    sget-object v1, Lcom/santander/one/domain/common/locale/AppLanguage;->PORTUGUESE:"
            "Lcom/santander/one/domain/common/locale/AppLanguage;\n\n"
            "    invoke-virtual {v1}, Lcom/santander/one/domain/common/locale/AppLanguage;"
            "->getLanguage()Ljava/lang/String;\n\n"
            "    move-result-object v1\n\n"
            "    iput-object v1, p0, Luu/a;->j:Ljava/lang/String;",
            "    sget-object v1, Lcom/santander/one/domain/common/locale/AppLanguage;->ENGLISH:"
            "Lcom/santander/one/domain/common/locale/AppLanguage;\n\n"
            "    invoke-virtual {v1}, Lcom/santander/one/domain/common/locale/AppLanguage;"
            "->getLanguage()Ljava/lang/String;\n\n"
            "    move-result-object v1\n\n"
            "    iput-object v1, p0, Luu/a;->j:Ljava/lang/String;",
        )
        pt_config.write_text(text, encoding="utf-8")
        print("  Portugal config defaultLanguage -> en")

    login_prefs = PATCHED_DIR / "smali_classes11" / "Sy" / "b.smali"
    patch_smali_method(
        login_prefs,
        "public e()Z",
        """.method public e()Z
    .locals 1

    const/4 v0, 0x0

    return v0
.end method""",
    )
    print("  Skip first-run language picker")

    lang_repo = PATCHED_DIR / "smali_classes10" / "Wm" / "b.smali"
    patch_smali_method(
        lang_repo,
        "public e()Lcom/santander/one/domain/common/locale/AppLanguage;",
        """.method public e()Lcom/santander/one/domain/common/locale/AppLanguage;
    .locals 1

    sget-object v0, Lcom/santander/one/domain/common/locale/AppLanguage;->ENGLISH:Lcom/santander/one/domain/common/locale/AppLanguage;

    return-object v0
.end method""",
    )
    print("  Language repository effective locale -> ENGLISH")


def patch_disable_tealium_appset():
    """Tealium AdIdentifier calls AppSet with empty PairIP strings — skip offline."""
    print("Disabling Tealium AppSet lookup...")
    ad_id = PATCHED_DIR / "smali_classes3" / "com" / "tealium" / "adidentifier" / "AdIdentifier.smali"
    patch_smali_method(
        ad_id,
        "public final i(Landroid/content/Context;)V",
        """.method public final i(Landroid/content/Context;)V
    .locals 0

    return-void
.end method""",
    )
    print("  Tealium AppSet disabled")


def patch_disable_marketing_cloud():
    """Skip Salesforce Marketing Cloud SDK init (uses VM-protected strings, not needed offline)."""
    print("Disabling Salesforce Marketing Cloud SDK...")
    salesforce_ds = PATCHED_DIR / "smali_classes12" / "sG.1" / "h.smali"
    patch_smali_method(
        salesforce_ds,
        "public constructor <init>(Landroid/app/Application;LsG/i;LVr/b;)V",
        """.method public constructor <init>(Landroid/app/Application;LsG/i;LVr/b;)V
    .locals 0

    invoke-direct {p0}, Ljava/lang/Object;-><init>()V

    iput-object p1, p0, LsG/h;->a:Landroid/app/Application;

    iput-object p2, p0, LsG/h;->b:LsG/i;

    iput-object p3, p0, LsG/h;->c:LVr/b;

    return-void
.end method""",
    )
    for method_sig in (
        "public c()V",
        "public e()V",
        "public f()V",
        "public g(Ljava/lang/String;)V",
    ):
        patch_smali_method(
            salesforce_ds,
            method_sig,
            f""".method {method_sig}
    .locals 0

    return-void
.end method""",
        )
    manifest = PATCHED_DIR / "AndroidManifest.xml"
    text = manifest.read_text(encoding="utf-8")
    for provider in (
        "com.salesforce.marketingcloud.MCInitContentProvider",
        "com.salesforce.marketingcloud.sfmcsdk.SFMCSdkInitContentProvider",
    ):
        pattern = rf'(<provider\b)([^>]*android:name="{re.escape(provider)}"[^>]*)(/?>)'

        def _disable_provider(match, _pattern=pattern):
            attrs = re.sub(r'\s*android:enabled="[^"]*"', "", match.group(2))
            return f'{match.group(1)}{attrs} android:enabled="false"{match.group(3)}'

        text = re.sub(pattern, _disable_provider, text)
    manifest.write_text(text, encoding="utf-8")
    print("  Marketing Cloud SDK disabled")


def patch_missing_drawables():
    """Fix drawables that reference split-APK assets missing from the base package."""
    print("Patching missing drawable resources...")
    default_thumb = PATCHED_DIR / "res" / "drawable" / "default_thumbnail.xml"
    default_thumb.write_text(
        """<?xml version="1.0" encoding="utf-8"?>
<layer-list xmlns:android="http://schemas.android.com/apk/res/android">
    <item android:gravity="fill" android:id="@id/bgThumbnail" android:drawable="@drawable/bg_thumbnail" />
</layer-list>
""",
        encoding="utf-8",
    )
    splash_bg = PATCHED_DIR / "res" / "drawable" / "splash_background.xml"
    splash_bg.write_text(
        """<?xml version="1.0" encoding="utf-8"?>
<layer-list xmlns:android="http://schemas.android.com/apk/res/android">
    <item android:gravity="fill" android:id="@id/bgSplash" android:drawable="@drawable/bg_splash" />
</layer-list>
""",
        encoding="utf-8",
    )
    drawables_xml = PATCHED_DIR / "res" / "values" / "drawables.xml"
    if drawables_xml.exists():
        text = drawables_xml.read_text(encoding="utf-8")
        text = text.replace(
            '<drawable name="img_thumbnail_slogan" />',
            '<drawable name="img_thumbnail_slogan">@drawable/bg_thumbnail</drawable>',
        )
        text = text.replace(
            '<drawable name="img_splash_slogan" />',
            '<drawable name="img_splash_slogan">@drawable/bg_splash</drawable>',
        )
        text = text.replace(
            '<drawable name="img_pg_clasic" />',
            '<drawable name="img_pg_clasic">@drawable/bg_thumbnail</drawable>',
        )
        for tip in (1, 2, 3):
            text = text.replace(
                f'<drawable name="loader_image_tip_{tip}" />',
                f'<drawable name="loader_image_tip_{tip}">@drawable/bg_thumbnail</drawable>',
            )
        drawables_xml.write_text(text, encoding="utf-8")

    dotted_white = """<?xml version="1.0" encoding="utf-8"?>
<shape android:shape="line" xmlns:android="http://schemas.android.com/apk/res/android">
    <stroke android:width="1dp" android:color="#FFFFFF" android:dashWidth="3dp" android:dashGap="4dp" />
</shape>
"""
    dotted_gray = """<?xml version="1.0" encoding="utf-8"?>
<shape android:shape="line" xmlns:android="http://schemas.android.com/apk/res/android">
    <stroke android:width="1dp" android:color="@color/medium_sky_gray" android:dashWidth="3dp" android:dashGap="4dp" />
</shape>
"""
    tile_bg = """<?xml version="1.0" encoding="utf-8"?>
<shape android:shape="rectangle" xmlns:android="http://schemas.android.com/apk/res/android">
    <solid android:color="#E0E0E0" />
</shape>
"""
    null_bitmap_fixes = {
        "dotted_separator_white.xml": dotted_white,
        "classic_pg_dotted_separator.xml": dotted_gray,
        "limit_pfm_dotted_separator.xml": dotted_gray,
        "limit_pfm_smart_pg_dotted_separator.xml": dotted_white,
        "private_menu_dotted_separator.xml": dotted_gray,
        "notification_tile_bg.xml": tile_bg,
    }
    drawable_dir = PATCHED_DIR / "res" / "drawable"
    for name, content in null_bitmap_fixes.items():
        (drawable_dir / name).write_text(content, encoding="utf-8")

    private_bg = PATCHED_DIR / "res" / "drawable" / "private_background.xml"
    if private_bg.exists():
        private_bg.write_text(
            """<?xml version="1.0" encoding="utf-8"?>
<layer-list xmlns:android="http://schemas.android.com/apk/res/android">
    <item android:drawable="@color/ui_background" />
    <item android:height="80dp" android:drawable="@color/ui_white" />
    <item android:gravity="top" android:drawable="@drawable/pg_placeholder_fake" android:top="80dp" />
    <item android:drawable="@drawable/background_gradient_loading" />
</layer-list>
""",
            encoding="utf-8",
        )
    print("  Fixed splash/thumbnail/null-bitmap drawables missing from split APKs")


def patch_sqlcipher_native():
    """Bundle libsqlcipher.so and ensure AppDelegate loads it at startup."""
    print("Patching SQLCipher native library...")
    lib_dir = PATCHED_DIR / "lib" / "arm64-v8a"
    lib_dir.mkdir(parents=True, exist_ok=True)
    lib_dst = lib_dir / "libsqlcipher.so"

    sqlcipher_aar = ROOT / "vendor" / "sqlcipher-android-4.9.0.aar"
    if not sqlcipher_aar.exists():
        print("  Downloading SQLCipher AAR (net.zetetic package)...")
        sqlcipher_aar.parent.mkdir(parents=True, exist_ok=True)
        run([
            "curl", "-sL",
            "https://repo1.maven.org/maven2/net/zetetic/sqlcipher-android/4.9.0/sqlcipher-android-4.9.0.aar",
            "-o", str(sqlcipher_aar),
        ])
    result = subprocess.run(
        ["unzip", "-p", str(sqlcipher_aar), "jni/arm64-v8a/libsqlcipher.so"],
        capture_output=True,
    )
    if result.returncode == 0 and result.stdout:
        lib_dst.write_bytes(result.stdout)
        print(f"  Bundled {lib_dst.relative_to(PATCHED_DIR)}")
    else:
        print("  WARNING: Could not extract libsqlcipher.so from AAR")

    app_delegate = PATCHED_DIR / "smali_classes9" / "com" / "santander" / "one" / "foundations" / "AppDelegate.smali"
    if app_delegate.exists():
        text = app_delegate.read_text(encoding="utf-8")
        if 'const-string p1, "sqlcipher"' not in text:
            text = text.replace(
                ".method public l(Landroid/app/Application;)V\n"
                "    .locals 0\n\n"
                "    return-void\n"
                ".end method",
                ".method public l(Landroid/app/Application;)V\n"
                "    .locals 0\n\n"
                '    const-string p1, "sqlcipher"\n\n'
                "    invoke-static {p1}, Ljava/lang/System;->loadLibrary(Ljava/lang/String;)V\n\n"
                "    return-void\n"
                ".end method",
            )
            app_delegate.write_text(text, encoding="utf-8")
    print("  SQLCipher native lib ready")


def patch_sqlcipher_load_early():
    """Call AppDelegate.l() during Application.w() — loads sqlcipher before DB access."""
    print("Patching early SQLCipher load...")
    app = PATCHED_DIR / "smali_classes11" / "com" / "santander" / "one" / "pt" / "app" / "AndroidApplication.smali"
    if app.exists():
        text = app.read_text(encoding="utf-8")
        needle = (
            ".method public final w()V\n"
            "    .locals 0\n\n"
            "    invoke-interface {p0}, Lcom/santander/one/foundations/AppDelegate;->k()V"
        )
        replacement = (
            ".method public final w()V\n"
            "    .locals 0\n\n"
            "    invoke-interface {p0, p0}, Lcom/santander/one/foundations/AppDelegate;->l(Landroid/app/Application;)V\n\n"
            "    invoke-interface {p0}, Lcom/santander/one/foundations/AppDelegate;->k()V"
        )
        if needle in text and replacement not in text:
            text = text.replace(needle, replacement)
            app.write_text(text, encoding="utf-8")
    print("  SQLCipher loadLibrary called at app startup")


def patch_root_checker_bypass():
    """Always report device as not rooted (libtoolChecker.so is in split APK)."""
    print("Patching root checker bypass...")
    root_impl = PATCHED_DIR / "smali_classes12" / "wL" / "a.smali"
    if root_impl.exists():
        text = root_impl.read_text(encoding="utf-8")
        old = (
            "    new-instance p2, LxL/b;\n\n"
            "    invoke-direct {p2}, LxL/b;-><init>()V\n\n"
            "    invoke-virtual {p2, p1}, LxL/b;->q(Landroid/content/Context;)Z\n\n"
            "    move-result p1\n\n"
            "    invoke-static {p1}, LcT/a;->a(Z)Ljava/lang/Boolean;\n\n"
            "    move-result-object p1\n\n"
            "    return-object p1"
        )
        new = (
            "    const/4 p1, 0x0\n\n"
            "    invoke-static {p1}, LcT/a;->a(Z)Ljava/lang/Boolean;\n\n"
            "    move-result-object p1\n\n"
            "    return-object p1"
        )
        if old in text:
            text = text.replace(old, new)
            root_impl.write_text(text, encoding="utf-8")
    print("  Root checker always returns not-rooted")


def patch_startup_error_dialog():
    """Disable PublicProducts startup error modal."""
    print("Patching startup error dialog...")
    fragment = (
        PATCHED_DIR
        / "smali_classes12"
        / "com"
        / "santander"
        / "one"
        / "publicproducts"
        / "ui"
        / "feature"
        / "home"
        / "PublicProductsFragment.smali"
    )
    if fragment.exists():
        text = fragment.read_text(encoding="utf-8")
        marker = ".method public final Gn()V\n    .locals"
        if "return-void\n\n    new-instance v0, Lcom/santander/flame" not in text:
            text = text.replace(
                ".method public final Gn()V\n    .locals 14\n\n"
                "    new-instance v0, Lcom/santander/flame/components/view/v2/bottomsheet/modal/FlameModal;",
                ".method public final Gn()V\n    .locals 14\n\n"
                "    return-void\n\n"
                "    new-instance v0, Lcom/santander/flame/components/view/v2/bottomsheet/modal/FlameModal;",
            )
            fragment.write_text(text, encoding="utf-8")
    print("  PublicProducts error dialog disabled")


def patch_public_products_error():
    """Don't show startup error dialog when public products list is empty."""
    print("Patching public products error dialog...")
    vm3 = (
        PATCHED_DIR
        / "smali_classes12"
        / "com"
        / "santander"
        / "one"
        / "publicproducts"
        / "ui"
        / "feature"
        / "home"
        / "PublicProductsViewModel$getPublicProducts$3.smali"
    )
    if vm3.exists():
        text = vm3.read_text(encoding="utf-8")
        text = text.replace(
            "    const/4 v2, 0x0\n\n"
            "    const/4 v3, 0x0\n\n"
            "    const/4 v4, 0x1\n\n"
            "    invoke-static/range {v1 .. v6}, Lcom/santander/one/publicproducts/ui/feature/home/PublicProductsViewModel$a;->b(",
            "    const/4 v2, 0x0\n\n"
            "    const/4 v3, 0x0\n\n"
            "    const/4 v4, 0x0\n\n"
            "    invoke-static/range {v1 .. v6}, Lcom/santander/one/publicproducts/ui/feature/home/PublicProductsViewModel$a;->b(",
        )
        vm3.write_text(text, encoding="utf-8")
    print("  Public products empty-list no longer triggers error dialog")


def patch_onboarding_language_null_safe():
    """Avoid NPE in onboarding language picker when AppLanguage is null."""
    print("Patching onboarding language null-safety...")
    delegate = PATCHED_DIR / "smali_classes11" / "com" / "santander" / "one" / "presentation" / "delegate" / "h.smali"
    if not delegate.exists():
        return
    text = delegate.read_text(encoding="utf-8")
    old = (
        ".method public fb(Lcom/santander/one/domain/common/locale/Language;)Ljava/lang/String;\n"
        "    .locals 1\n\n"
        "    invoke-virtual {p1}, Lcom/santander/one/domain/common/locale/Language;->getAppLanguage()"
        "Lcom/santander/one/domain/common/locale/AppLanguage;\n\n"
        "    move-result-object p1\n\n"
        "    invoke-virtual {p1}, Ljava/lang/Enum;->name()Ljava/lang/String;\n\n"
        "    move-result-object p1\n\n"
        "    sget-object v0, Ljava/util/Locale;->ROOT:Ljava/util/Locale;\n\n"
        "    invoke-virtual {p1, v0}, Ljava/lang/String;->toLowerCase(Ljava/util/Locale;)Ljava/lang/String;\n\n"
        "    move-result-object p1\n\n"
        "    return-object p1\n"
        ".end method"
    )
    new = (
        ".method public fb(Lcom/santander/one/domain/common/locale/Language;)Ljava/lang/String;\n"
        "    .locals 1\n\n"
        "    invoke-virtual {p1}, Lcom/santander/one/domain/common/locale/Language;->getAppLanguage()"
        "Lcom/santander/one/domain/common/locale/AppLanguage;\n\n"
        "    move-result-object p1\n\n"
        "    if-nez p1, :cond_0\n\n"
        "    const-string p1, \"en\"\n\n"
        "    return-object p1\n\n"
        "    :cond_0\n"
        "    invoke-virtual {p1}, Ljava/lang/Enum;->name()Ljava/lang/String;\n\n"
        "    move-result-object p1\n\n"
        "    if-nez p1, :cond_1\n\n"
        "    const-string p1, \"en\"\n\n"
        "    return-object p1\n\n"
        "    :cond_1\n"
        "    sget-object v0, Ljava/util/Locale;->ROOT:Ljava/util/Locale;\n\n"
        "    invoke-virtual {p1, v0}, Ljava/lang/String;->toLowerCase(Ljava/util/Locale;)Ljava/lang/String;\n\n"
        "    move-result-object p1\n\n"
        "    return-object p1\n"
        ".end method"
    )
    if old in text:
        text = text.replace(old, new)
        delegate.write_text(text, encoding="utf-8")
    print("  Onboarding language delegate patched")


def patch_legacy_generic_error_dialog():
    """Suppress legacy UseCaseCallback generic error modal at startup."""
    print("Patching legacy generic error handler...")
    handler = PATCHED_DIR / "smali_classes3" / "CR" / "b.smali"
    if handler.exists():
        text = handler.read_text(encoding="utf-8")
        old_e = (
            ".method public e()V\n"
            "    .locals 1\n\n"
            "    new-instance v0, Lcom/santander/one/error/ui/feature/dialog/view/ErrorDialogFragment;\n\n"
            "    invoke-direct {v0}, Lcom/santander/one/error/ui/feature/dialog/view/ErrorDialogFragment;-><init>()V\n\n"
            "    invoke-virtual {p0, v0}, LCR/b;->d(Landroidx/fragment/app/DialogFragment;)V\n\n"
            "    return-void\n"
            ".end method\n\n"
            ".method public showGenericError()V\n"
            "    .locals 0\n\n"
            "    invoke-virtual {p0}, LCR/b;->e()V\n\n"
            "    return-void\n"
            ".end method"
        )
        new_e = (
            ".method public e()V\n"
            "    .locals 0\n\n"
            "    return-void\n"
            ".end method\n\n"
            ".method public showGenericError()V\n"
            "    .locals 0\n\n"
            "    return-void\n"
            ".end method"
        )
        if old_e in text:
            text = text.replace(old_e, new_e)
            handler.write_text(text, encoding="utf-8")
    print("  Legacy generic error dialog suppressed")


def patch_public_products_assets():
    """Ensure bundled public products JSON is available for all language prefixes."""
    print("Patching public products assets...")
    san_dir = PATCHED_DIR / "assets" / "default" / "apps" / "SAN"
    if not san_dir.exists():
        san_dir.mkdir(parents=True, exist_ok=True)
    mock_data = ROOT / "mock-server" / "data"
    for lang in ("pt", "en"):
        mock_src = mock_data / f"public-products-{lang}.json"
        if mock_src.exists():
            shutil.copy2(mock_src, san_dir / f"{lang}_public_products.json")
    pt_file = san_dir / "pt_public_products.json"
    if pt_file.exists():
        shutil.copy2(pt_file, san_dir / "public_products.json")
    for lang in ("pt", "en"):
        src = APKTOOL_SRC / "assets" / "default" / "apps" / "SAN" / f"{lang}_public_products.json"
        dst = san_dir / f"{lang}_public_products.json"
        if src.exists() and not dst.exists():
            shutil.copy2(src, dst)
    print("  Public products JSON assets ensured")


def patch_context_wrapper():
    """Fix AppCompat context wrapper that relies on VM-initialized string constants."""
    context_wrapper = PATCHED_DIR / "smali_classes2" / "l" / "d.smali"
    if not context_wrapper.exists():
        return
    text = context_wrapper.read_text(encoding="utf-8")
    text = text.replace(
        "    sget-object v0, Lorg/apache/poi/ss/formula/eval/EY/lFMU;->BmDeOqmsYkWrJp:Ljava/lang/String;\n\n"
        "    invoke-virtual {v0, p1}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z",
        '    const-string v0, "layout_inflater"\n\n'
        "    invoke-virtual {v0, p1}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z",
    )
    context_wrapper.write_text(text, encoding="utf-8")
    print("  Patched AppCompat context wrapper (layout_inflater)")


def patch_ssl_pinning():
    """Replace CertificatePinner builder chain with empty builder in OkHttpModule.smali"""
    smali = PATCHED_DIR / "smali_classes11" / "com" / "santander" / "one" / "pt" / "di" / "OkHttpModule.smali"
    if not smali.exists():
        for candidate in PATCHED_DIR.glob("**/OkHttpModule.smali"):
            smali = candidate
            break
    if not smali.exists():
        print("  WARNING: OkHttpModule.smali not found — SSL pinning not patched")
        return

    text = smali.read_text(encoding="utf-8")
    # Replace the entire provideCertificatePinner method body with empty pinner
    pattern = r"(\.method public final provideCertificatePinner\(\)Lokhttp3/CertificatePinner;.*?)(\.end method)"
    replacement = r""".method public final provideCertificatePinner()Lokhttp3/CertificatePinner;
    .locals 1

    new-instance v0, Lokhttp3/CertificatePinner$Builder;

    invoke-direct {v0}, Lokhttp3/CertificatePinner$Builder;-><init>()V

    invoke-virtual {v0}, Lokhttp3/CertificatePinner$Builder;->build()Lokhttp3/CertificatePinner;

    move-result-object v0

    return-object v0
.end method"""
    new_text, n = re.subn(pattern, replacement, text, count=1, flags=re.DOTALL)
    if n:
        smali.write_text(new_text, encoding="utf-8")
        print(f"Patched SSL pinning in {smali.name}")
    else:
        print("  WARNING: Could not patch provideCertificatePinner method")


def rename_package_smali_dirs():
    """Move R.smali and provider classes to new package path."""
    for smali_root in PATCHED_DIR.glob("smali*"):
        old_dir = smali_root / OLD_PACKAGE_PATH
        new_dir = smali_root / NEW_PACKAGE_PATH
        if old_dir.exists():
            new_dir.parent.mkdir(parents=True, exist_ok=True)
            if new_dir.exists():
                shutil.rmtree(new_dir)
            shutil.move(str(old_dir), str(new_dir))
            print(f"  Moved {old_dir.relative_to(PATCHED_DIR)} -> {new_dir.relative_to(PATCHED_DIR)}")


def build_apk():
    print("Building APK with apktool...")
    run(["apktool", "b", str(PATCHED_DIR), "-o", str(OUTPUT_APK)])


def sign_apk():
    keystore = ROOT / "clone-debug.keystore"
    if not keystore.exists():
        print("Creating debug keystore...")
        run([
            "keytool", "-genkeypair",
            "-v",
            "-keystore", str(keystore),
            "-alias", "clonekey",
            "-keyalg", "RSA",
            "-keysize", "2048",
            "-validity", "10000",
            "-storepass", "clonepass",
            "-keypass", "clonepass",
            "-dname", "CN=Clone Demo, OU=Dev, O=Azemon, L=Lisbon, ST=Lisbon, C=PT",
        ])

    signed = ROOT / "SantanderClone-signed.apk"
    aligned = ROOT / "SantanderClone-aligned.apk"

    build_tools = Path.home() / "Library" / "Android" / "sdk" / "build-tools"
    apksigner = None
    zipalign = None
    if build_tools.exists():
        versions = sorted(build_tools.iterdir(), reverse=True)
        for v in versions:
            if (v / "apksigner").exists():
                apksigner = v / "apksigner"
            if (v / "zipalign").exists():
                zipalign = v / "zipalign"
            if apksigner and zipalign:
                break

    if zipalign:
        run([str(zipalign), "-f", "4", str(OUTPUT_APK), str(aligned)])
        input_apk = aligned
    else:
        input_apk = OUTPUT_APK
        print("  zipalign not found — skipping alignment")

    if apksigner:
        run([
            str(apksigner), "sign",
            "--ks", str(keystore),
            "--ks-pass", "pass:clonepass",
            "--key-pass", "pass:clonepass",
            "--out", str(signed),
            str(input_apk),
        ])
        print(f"\nSigned APK: {signed}")
    else:
        print("\n  apksigner not found. Sign manually:")
        print(f"  jarsigner -keystore {keystore} -storepass clonepass {OUTPUT_APK} clonekey")


def main():
    if not APKTOOL_SRC.exists():
        print("ERROR: Run apktool decompilation first (apktool d Santander.apk -o apktool)")
        sys.exit(1)

    global URL_REPLACEMENTS
    parser = argparse.ArgumentParser(description="Patch Santander APK for mock API")
    parser.add_argument(
        "--mock-host",
        default=os.environ.get("MOCK_HOST", DEFAULT_MOCK_HOST),
        help="Mock API base URL (e.g. https://your-app.up.railway.app)",
    )
    args = parser.parse_args()
    URL_REPLACEMENTS = build_url_replacements(args.mock_host)

    print("=== Santander Clone APK Patcher ===\n")
    print(f"  Mock API: {args.mock_host.rstrip('/')}\n")
    copy_apktool_tree()
    rename_package_smali_dirs()
    patch_all_files()
    patch_manifest()
    patch_pairip_bypass()
    patch_vm_reflection_bypass()
    patch_kotlin_builtin_strings()
    patch_pairip_string_defaults()
    patch_missing_drawables()
    patch_gms_preconditions()
    patch_gms_connection_tracker()
    patch_disable_tealium_appset()
    patch_default_english_language()
    patch_disable_marketing_cloud()
    patch_sqlcipher_native()
    patch_sqlcipher_load_early()
    patch_root_checker_bypass()
    patch_startup_error_dialog()
    patch_public_products_error()
    patch_onboarding_language_null_safe()
    patch_legacy_generic_error_dialog()
    patch_public_products_assets()
    patch_context_wrapper()
    patch_ssl_pinning()
    build_apk()
    sign_apk()
    print("\nDone! Install SantanderClone-signed.apk and start mock-server.")


if __name__ == "__main__":
    main()
