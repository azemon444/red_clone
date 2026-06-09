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
            r"\n    const/4 v0, 0x0\n\n    sget-object v0, Lq2/RCrk/GeeKAbXKd;->ITYYlRiFvb:Ljava/lang/String;\n\n    invoke-static {v0}, LWT/i;->b\(Ljava/lang/String;\)LWT/b;",
            '\n    const-string v0, "Comparable"\n\n    invoke-static {v0}, LWT/i;->b(Ljava/lang/String;)LWT/b;',
        ),
        (
            r"\n    const/4 v2, 0x0\n\n    sget-object v2, Lu3/aan/HiKReLihbCmCBQ;->oRDTx:Ljava/lang/String;\n\n    invoke-static {v2}, LWT/i;->c\(Ljava/lang/String;\)LWT/b;",
            '\n    const-string v2, "Collection"\n\n    invoke-static {v2}, LWT/i;->c(Ljava/lang/String;)LWT/b;',
        ),
    ]
    for pattern, replacement in replacements:
        text, n = re.subn(pattern, replacement, text, count=1)
        if not n:
            text = text.replace(
                "    sget-object v0, Lq2/RCrk/GeeKAbXKd;->ITYYlRiFvb:Ljava/lang/String;\n\n"
                "    invoke-static {v0}, LWT/i;->b(Ljava/lang/String;)LWT/b;",
                '    const-string v0, "Comparable"\n\n'
                "    invoke-static {v0}, LWT/i;->b(Ljava/lang/String;)LWT/b;",
            )
            text = text.replace(
                "    sget-object v2, Lu3/aan/HiKReLihbCmCBQ;->oRDTx:Ljava/lang/String;\n\n"
                "    invoke-static {v2}, LWT/i;->c(Ljava/lang/String;)LWT/b;",
                '    const-string v2, "Collection"\n\n'
                "    invoke-static {v2}, LWT/i;->c(Ljava/lang/String;)LWT/b;",
            )
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
        pattern = rf'(<provider\b)([^/>]*android:name="{re.escape(provider)}"[^/>]*)(/>|>)'

        def _disable_provider(match, _pattern=pattern):
            attrs = re.sub(r'\s*android:enabled="[^"]*"', "", match.group(2))
            if match.group(3) == "/>":
                return f'{match.group(1)}{attrs} android:enabled="false" />'
            return f'{match.group(1)}{attrs} android:enabled="false">'

        text = re.sub(pattern, _disable_provider, text)
    manifest.write_text(text, encoding="utf-8")
    print("  Marketing Cloud SDK disabled")


def patch_missing_drawables():
    """Fix drawables that reference split-APK assets missing from the base package."""
    print("Patching missing drawable resources...")
    drawable_dir = PATCHED_DIR / "res" / "drawable"
    drawable_dir.mkdir(parents=True, exist_ok=True)
    brand_fill = """<?xml version="1.0" encoding="utf-8"?>
<shape android:shape="rectangle" xmlns:android="http://schemas.android.com/apk/res/android">
    <solid android:color="@color/santander_red" />
</shape>
"""
    (drawable_dir / "bg_splash.xml").write_text(brand_fill, encoding="utf-8")
    (drawable_dir / "bg_thumbnail.xml").write_text(brand_fill, encoding="utf-8")
    default_thumb = drawable_dir / "default_thumbnail.xml"
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
    transfer_red = """<?xml version="1.0" encoding="utf-8"?>
<vector android:height="32.0dp" android:width="32.0dp" android:viewportWidth="32.0" android:viewportHeight="32.0"
  xmlns:android="http://schemas.android.com/apk/res/android">
    <path android:fillColor="#ec0000" android:pathData="M8.38,8.867c0.32,0 0.58,0.262 0.58,0.586 0,0.292 -0.21,0.534 -0.486,0.58l-0.094,0.007L7.162,10.04c-0.256,2.042 -1.8,3.664 -3.787,4.015l-0.215,0.032L3.16,18.9c2.019,0.259 3.623,1.82 3.97,3.83l0.032,0.217h12.877c0.256,-2.042 1.8,-3.664 3.787,-4.014l0.215,-0.033v-4.812c-2.019,-0.258 -3.623,-1.82 -3.97,-3.83l-0.032,-0.217L18.82,10.041c-0.32,0 -0.58,-0.263 -0.58,-0.587 0,-0.292 0.21,-0.533 0.486,-0.579l0.094,-0.007h5.8c0.29,0 0.528,0.212 0.573,0.491l0.008,0.095L25.2,11.5l1.65,0.001 0.045,0.003 0.045,-0.003c0.288,0 0.527,0.213 0.572,0.492l0.008,0.095 -0.001,2.244c0.059,-0.02 0.122,-0.031 0.188,-0.031h1.344l0.044,0.003 0.045,-0.003c0.288,0 0.527,0.213 0.572,0.492l0.008,0.095v13.266c0,0.292 -0.21,0.534 -0.486,0.58l-0.094,0.007L6.78,28.741c-0.32,0 -0.58,-0.263 -0.58,-0.587v-0.004,-1.572c0,-0.053 0.007,-0.104 0.02,-0.153L4.58,26.425c-0.32,0 -0.58,-0.263 -0.58,-0.587v-0.004,-1.572c0,-0.049 0.006,-0.097 0.018,-0.142L2.58,24.12c-0.289,0 -0.528,-0.212 -0.572,-0.49L2,23.532L2,9.453c0,-0.292 0.21,-0.533 0.486,-0.579l0.094,-0.007h5.8zM27.519,15.442v10.395c0,0.292 -0.21,0.534 -0.485,0.58l-0.094,0.007L7.34,26.424c0.013,0.049 0.02,0.1 0.02,0.153v0.989h21.2l-0.001,-12.093h-0.852c-0.066,0 -0.129,-0.01 -0.188,-0.03zM26.359,12.673L25.2,12.673v10.86c0,0.292 -0.21,0.534 -0.485,0.579l-0.094,0.008 -19.479,-0.001c0.012,0.045 0.018,0.093 0.018,0.143v0.988h21.2l-0.001,-12.577zM3.16,20.073v2.873h2.841c-0.245,-1.47 -1.388,-2.625 -2.841,-2.874zM24.04,20.073c-1.39,0.237 -2.495,1.305 -2.804,2.683l-0.037,0.19h2.842v-2.874zM13.93,3.103l0.08,0.068 3.48,3.52c0.227,0.229 0.227,0.6 0,0.83 -0.113,0.114 -0.261,0.171 -0.41,0.171 -0.118,0 -0.237,-0.036 -0.338,-0.11l-0.072,-0.062 -2.49,-2.518v7.443c1.963,0.288 3.48,1.984 3.48,4.047 0,2.264 -1.821,4.107 -4.06,4.107 -2.238,0 -4.06,-1.843 -4.06,-4.107 0,-1.994 1.418,-3.646 3.286,-4.014l0.194,-0.033L13.02,5.003L10.53,7.52c-0.226,0.23 -0.593,0.23 -0.82,0 -0.201,-0.203 -0.224,-0.52 -0.067,-0.748l0.067,-0.081 3.48,-3.52c0.202,-0.204 0.514,-0.226 0.74,-0.068zM13.6,13.56c-1.599,0 -2.9,1.315 -2.9,2.933 0,1.618 1.301,2.933 2.9,2.933 1.6,0 2.9,-1.315 2.9,-2.933 0,-1.618 -1.3,-2.933 -2.9,-2.933zM24.04,10.04L21.2,10.04c0.234,1.405 1.29,2.524 2.653,2.836l0.188,0.038L24.041,10.04zM6.001,10.04L3.16,10.04v2.874c1.453,-0.249 2.596,-1.405 2.841,-2.874z" android:fillType="evenOdd" />
</vector>
"""
    (drawable_dir / "icn_transfer_red.xml").write_text(transfer_red, encoding="utf-8")
    public_xml = PATCHED_DIR / "res" / "values" / "public.xml"
    if public_xml.exists():
        text = public_xml.read_text(encoding="utf-8")
        needle = '    <public type="drawable" name="icn_transfer_packages" id="0x7f080a90" />\n'
        insert = (
            needle
            + '    <public type="drawable" name="icn_transfer_red" id="0x7f080a91" />\n'
        )
        if "icn_transfer_red" not in text and needle in text:
            text = text.replace(needle, insert)
        pending_needle = (
            '    <public type="drawable" name="icn_send_pending" id="0x7f080a56" />\n'
        )
        programmed_insert = (
            pending_needle
            + '    <public type="drawable" name="icn_send_programmed" id="0x7f080a57" />\n'
        )
        if "icn_send_programmed" not in text and pending_needle in text:
            text = text.replace(pending_needle, programmed_insert)
        if text != public_xml.read_text(encoding="utf-8"):
            public_xml.write_text(text, encoding="utf-8")
    pending_src = PATCHED_DIR / "res" / "drawable" / "icn_send_pending.xml"
    programmed_dst = drawable_dir / "icn_send_programmed.xml"
    if pending_src.exists() and not programmed_dst.exists():
        shutil.copy2(pending_src, programmed_dst)
    print("  Fixed splash/thumbnail/null-bitmap drawables missing from split APKs")


GP_SEED_SMALI = """.class public Lcom/azemon/santanderclone/GpSeed;
.super Ljava/lang/Object;
.source "GpSeed.java"


# direct methods
.method public constructor <init>()V
    .locals 0

    invoke-direct {p0}, Ljava/lang/Object;-><init>()V

    return-void
.end method

.method public static a(Landroid/content/Context;)Lcom/santander/one/pt/data/remote/services/pg/response/PgDataDTO;
    .locals 4

    :try_start_0
    invoke-virtual {p0}, Landroid/content/Context;->getAssets()Landroid/content/res/AssetManager;

    move-result-object p0

    const-string v0, "default/apps/SAN/global_position_seed.json"

    invoke-virtual {p0, v0}, Landroid/content/res/AssetManager;->open(Ljava/lang/String;)Ljava/io/InputStream;

    move-result-object p0

    new-instance v0, Ljava/util/Scanner;

    invoke-direct {v0, p0}, Ljava/util/Scanner;-><init>(Ljava/io/InputStream;)V

    const-string p0, "\\\\A"

    invoke-virtual {v0, p0}, Ljava/util/Scanner;->useDelimiter(Ljava/lang/String;)Ljava/util/Scanner;

    move-result-object p0

    invoke-virtual {p0}, Ljava/util/Scanner;->next()Ljava/lang/String;

    move-result-object p0

    new-instance v0, Lcom/google/gson/e;

    invoke-direct {v0}, Lcom/google/gson/e;-><init>()V

    const-class v1, Lcom/santander/one/pt/data/remote/services/pg/response/PgDataDTO;

    invoke-virtual {v0, p0, v1}, Lcom/google/gson/e;->m(Ljava/lang/String;Ljava/lang/Class;)Ljava/lang/Object;

    move-result-object p0

    check-cast p0, Lcom/santander/one/pt/data/remote/services/pg/response/PgDataDTO;
    :try_end_0
    .catch Ljava/lang/Exception; {:try_start_0 .. :try_end_0} :catch_0

    return-object p0

    :catch_0
    const/4 p0, 0x0

    return-object p0
.end method

.method public static b(Landroidx/fragment/app/Fragment;)V
    .locals 1

    :try_start_0
    instance-of v0, p0, Lcom/santander/one/gp/legacy/ui/simple/SimplePGPresenter;

    if-eqz v0, :cond_end

    check-cast p0, Lcom/santander/one/gp/legacy/ui/simple/SimplePGPresenter;

    iget-object v0, p0, Lcom/santander/one/gp/legacy/ui/simple/SimplePGPresenter;->Q7:Lcom/santander/one/gp/legacy/ui/simple/SimplePGView;

    if-eqz v0, :cond_end

    invoke-virtual {v0}, Lcom/santander/one/gp/legacy/ui/simple/SimplePGView;->z0()V
    :try_end_0
    .catch Ljava/lang/Exception; {:try_start_0 .. :try_end_0} :catch_0

    :cond_end
    return-void

    :catch_0
    return-void
.end method

.method public static c(Landroidx/fragment/app/Fragment;)V
    .locals 2

    :try_start_0
    instance-of v0, p0, Lcom/santander/one/gp/legacy/ui/simple/SimplePGPresenter;

    if-eqz v0, :cond_end

    check-cast p0, Lcom/santander/one/gp/legacy/ui/simple/SimplePGPresenter;

    invoke-virtual {p0}, Les/bancosantander/apps/mobile/features/private_home/pg/BasePGPresenter;->e8()Les/bancosantander/apps/domain/domain_objects/common/GlobalPositionWrapper;

    move-result-object v0

    if-nez v0, :cond_have_wrapper

    invoke-virtual {p0}, Landroidx/fragment/app/Fragment;->getContext()Landroid/content/Context;

    move-result-object v0

    if-nez v0, :cond_ctx

    invoke-static {}, Landroid/app/ActivityThread;->currentApplication()Landroid/app/Application;

    move-result-object v0

    :cond_ctx
    invoke-static {v0}, Lcom/azemon/santanderclone/GpSeed;->d(Landroid/content/Context;)Les/bancosantander/apps/domain/domain_objects/common/GlobalPositionWrapper;

    move-result-object v0

    if-eqz v0, :cond_hide_only

    invoke-virtual {p0, v0}, Les/bancosantander/apps/mobile/features/private_home/pg/BasePGPresenter;->Rs(Les/bancosantander/apps/domain/domain_objects/common/GlobalPositionWrapper;)V

    :cond_have_wrapper
    invoke-virtual {p0}, Les/bancosantander/apps/mobile/features/private_home/pg/BasePGPresenter;->Rr()V

    invoke-static {}, Ljava/util/Collections;->emptyList()Ljava/util/List;

    move-result-object v1

    invoke-virtual {p0, v1}, Lcom/santander/one/gp/legacy/ui/simple/SimplePGPresenter;->ks(Ljava/util/List;)V

    invoke-static {p0}, Lcom/azemon/santanderclone/GpSeed;->b(Landroidx/fragment/app/Fragment;)V

    goto :cond_end

    :cond_hide_only
    invoke-static {p0}, Lcom/azemon/santanderclone/GpSeed;->b(Landroidx/fragment/app/Fragment;)V

    :cond_end
    return-void
    :try_end_0
    .catch Ljava/lang/Exception; {:try_start_0 .. :try_end_0} :catch_0

    :catch_0
    invoke-static {p0}, Lcom/azemon/santanderclone/GpSeed;->b(Landroidx/fragment/app/Fragment;)V

    return-void
.end method

.method public static d(Landroid/content/Context;)Les/bancosantander/apps/domain/domain_objects/common/GlobalPositionWrapper;
    .locals 0

    invoke-static {p0}, Lcom/azemon/santanderclone/GpSeedHelper;->build(Landroid/content/Context;)Les/bancosantander/apps/domain/domain_objects/common/GlobalPositionWrapper;

    move-result-object p0

    return-object p0
.end method
"""

GP_SEED_HELPER_SMALI = """.class public Lcom/azemon/santanderclone/GpSeedHelper;
.super Ljava/lang/Object;
.source "GpSeedHelper.java"


# direct methods
.method public constructor <init>()V
    .locals 0

    invoke-direct {p0}, Ljava/lang/Object;-><init>()V

    return-void
.end method

.method public static build(Landroid/content/Context;)Les/bancosantander/apps/domain/domain_objects/common/GlobalPositionWrapper;
    .registers 19

    move-object/from16 v0, p0

    :try_start_0
    invoke-static {v0}, Lcom/azemon/santanderclone/GpSeed;->a(Landroid/content/Context;)Lcom/santander/one/pt/data/remote/services/pg/response/PgDataDTO;

    move-result-object v0

    if-eqz v0, :catch_0

    const-string v1, "000365542813020"

    const/4 v2, 0x0

    invoke-static {v0, v1, v2}, Lc/e;->a(Lcom/santander/one/pt/data/remote/services/pg/response/PgDataDTO;Ljava/lang/String;Lcom/santander/one/pt/data/remote/services/customer/model/CustomerResponseDTO;)Lcom/santander/one/sanlibrary/v3/common/dto/GlobalPositionDTO;

    move-result-object v0

    const-string v1, "Shuaib"

    invoke-virtual {v0, v1}, Lcom/santander/one/sanlibrary/v3/common/dto/GlobalPositionDTO;->setClientName(Ljava/lang/String;)V

    invoke-virtual {v0, v1}, Lcom/santander/one/sanlibrary/v3/common/dto/GlobalPositionDTO;->setClientNameWithoutSurname(Ljava/lang/String;)V

    new-instance v1, Lcom/santander/one/data/feature/userprefs/dto/UserPrefDTO;

    invoke-direct {v1}, Lcom/santander/one/data/feature/userprefs/dto/UserPrefDTO;-><init>()V

    invoke-static {}, Les/bancosantander/apps/domain/domain_objects/config/GlobalPositionConfig;->create()Les/bancosantander/apps/domain/domain_objects/config/GlobalPositionConfig;

    move-result-object v7

    new-instance v8, Ljava/util/HashMap;

    invoke-direct {v8}, Ljava/util/HashMap;-><init>()V

    new-instance v9, Ljava/util/HashMap;

    invoke-direct {v9}, Ljava/util/HashMap;-><init>()V

    new-instance v10, Ljava/util/HashMap;

    invoke-direct {v10}, Ljava/util/HashMap;-><init>()V

    new-instance v11, Ljava/util/HashMap;

    invoke-direct {v11}, Ljava/util/HashMap;-><init>()V

    const/4 v12, 0x0

    invoke-static {}, Ljava/util/Collections;->emptyList()Ljava/util/List;

    move-result-object v13

    invoke-static {}, Ljava/util/Collections;->emptyList()Ljava/util/List;

    move-result-object v14

    const/4 v15, 0x0

    const/16 v16, 0x0

    const/4 v2, 0x0

    const/4 v3, 0x0

    const/4 v4, 0x0

    new-instance v5, Luu/a;

    invoke-direct {v5}, Luu/a;-><init>()V

    new-instance v6, Liz/a;

    invoke-direct {v6}, Liz/a;-><init>()V

    new-instance v17, Liz/b;

    invoke-direct/range {v17 .. v17}, Liz/b;-><init>()V

    invoke-static/range {v0 .. v17}, Les/bancosantander/apps/domain/domain_objects/common/GlobalPositionWrapper;->createFromDTO(Lcom/santander/one/sanlibrary/v3/common/dto/GlobalPositionDTO;Lcom/santander/one/data/feature/userprefs/dto/UserPrefDTO;ZZZLUe/d;LUe/b;Les/bancosantander/apps/domain/domain_objects/config/GlobalPositionConfig;Ljava/util/Map;Ljava/util/Map;Ljava/util/Map;Ljava/util/Map;Lcom/santander/one/sanlibrary/v3/common/dto/transaction/CardSuperSpeedListDTO;Ljava/util/List;Ljava/util/List;Lcom/santander/one/publicfiles/accountsinfo/model/AccountInfoWrapperDTO;LiR/a;LUe/k;)Les/bancosantander/apps/domain/domain_objects/common/GlobalPositionWrapper;

    move-result-object v0

    return-object v0

    :catch_0
    const/4 v0, 0x0

    return-object v0

    :try_end_0
    .catch Ljava/lang/Exception; {:try_start_0 .. :try_end_0} :catch_0
.end method
"""


def patch_gp_seed_fallback():
    """Bundle offline GP JSON and fall back when API/session GP is missing."""
    print("Patching global position seed fallback...")
    seed_src = ROOT / "mock-server" / "data" / "global-position.json"
    seed_dst = PATCHED_DIR / "assets" / "default" / "apps" / "SAN" / "global_position_seed.json"
    if seed_src.exists():
        seed_dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(seed_src, seed_dst)

    gp_seed_dir = PATCHED_DIR / "smali" / "com" / "azemon" / "santanderclone"
    gp_seed_dir.mkdir(parents=True, exist_ok=True)
    (gp_seed_dir / "GpSeed.smali").write_text(GP_SEED_SMALI, encoding="utf-8")
    gp_helper_dir = PATCHED_DIR / "smali_classes3" / "com" / "azemon" / "santanderclone"
    gp_helper_dir.mkdir(parents=True, exist_ok=True)
    (gp_helper_dir / "GpSeedHelper.smali").write_text(GP_SEED_HELPER_SMALI, encoding="utf-8")

    bsan_gp = PATCHED_DIR / "smali" / "b.1" / "b.smali"
    if bsan_gp.exists():
        text = bsan_gp.read_text(encoding="utf-8")
        old = (
            "    invoke-virtual {v0}, Lcom/santander/one/pt/data/remote/services/session/model/PortugalSessionData;->getGlobalPosition()Lcom/santander/one/pt/data/remote/services/pg/response/PgDataDTO;\n\n"
            "    move-result-object v2\n\n"
            "    iget-object v3, p0, Lb/b;->b:LSy/a;"
        )
        new = (
            "    invoke-virtual {v0}, Lcom/santander/one/pt/data/remote/services/session/model/PortugalSessionData;->getGlobalPosition()Lcom/santander/one/pt/data/remote/services/pg/response/PgDataDTO;\n\n"
            "    move-result-object v2\n\n"
            "    if-nez v2, :gp_ready\n\n"
            "    invoke-static {}, Landroid/app/ActivityThread;->currentApplication()Landroid/app/Application;\n\n"
            "    move-result-object v2\n\n"
            "    invoke-static {v2}, Lcom/azemon/santanderclone/GpSeed;->a(Landroid/content/Context;)Lcom/santander/one/pt/data/remote/services/pg/response/PgDataDTO;\n\n"
            "    move-result-object v2\n\n"
            "    :gp_ready\n"
            "    iget-object v3, p0, Lb/b;->b:LSy/a;"
        )
        if old in text:
            text = text.replace(old, new)
            bsan_gp.write_text(text, encoding="utf-8")

    gp_repo = PATCHED_DIR / "smali_classes11" / "zx.1" / "d.smali"
    if gp_repo.exists():
        text = gp_repo.read_text(encoding="utf-8")
        if ":gp_try_seed" not in text:
            old_fail = (
                "    instance-of v1, v0, LuP/a$a;\n\n"
                "    if-eqz v1, :cond_0\n\n"
                "    new-instance v1, LuP/a$a;\n\n"
                "    new-instance v2, Lyf/a;\n\n"
                "    check-cast v0, LuP/a$a;\n\n"
                "    invoke-virtual {v0}, LuP/a$a;->a()Ljava/lang/Object;\n\n"
                "    move-result-object v0\n\n"
                "    check-cast v0, Lcom/santander/one/pt/data/remote/rest/PortugalError;\n\n"
                "    invoke-virtual {v0}, Lcom/santander/one/pt/data/remote/rest/PortugalError;->getStatusCode()I\n\n"
                "    move-result v0\n\n"
                "    invoke-static {v0}, Ljava/lang/String;->valueOf(I)Ljava/lang/String;\n\n"
                "    move-result-object v0\n\n"
                "    const-string v3, \"\"\n\n"
                "    invoke-direct {v2, v0, v3}, Lyf/a;-><init>(Ljava/lang/String;Ljava/lang/String;)V\n\n"
                "    invoke-direct {v1, v2}, LuP/a$a;-><init>(Ljava/lang/Object;)V\n\n"
                "    return-object v1\n\n"
                "    :cond_0\n"
            )
            new_fail = (
                "    instance-of v1, v0, LuP/a$a;\n\n"
                "    if-nez v1, :gp_try_seed\n\n"
                "    goto :gp_after_remote\n\n"
                "    :gp_try_seed\n"
                "    invoke-static {}, Landroid/app/ActivityThread;->currentApplication()Landroid/app/Application;\n\n"
                "    move-result-object v1\n\n"
                "    invoke-static {v1}, Lcom/azemon/santanderclone/GpSeed;->a(Landroid/content/Context;)Lcom/santander/one/pt/data/remote/services/pg/response/PgDataDTO;\n\n"
                "    move-result-object v1\n\n"
                "    if-eqz v1, :cond_0\n\n"
                "    new-instance v0, LuP/a$b;\n\n"
                "    invoke-direct {v0, v1}, LuP/a$b;-><init>(Ljava/lang/Object;)V\n\n"
                "    :gp_after_remote\n"
                "    instance-of v1, v0, LuP/a$a;\n\n"
                "    if-eqz v1, :cond_0\n\n"
                "    new-instance v1, LuP/a$a;\n\n"
                "    new-instance v2, Lyf/a;\n\n"
                "    check-cast v0, LuP/a$a;\n\n"
                "    invoke-virtual {v0}, LuP/a$a;->a()Ljava/lang/Object;\n\n"
                "    move-result-object v0\n\n"
                "    check-cast v0, Lcom/santander/one/pt/data/remote/rest/PortugalError;\n\n"
                "    invoke-virtual {v0}, Lcom/santander/one/pt/data/remote/rest/PortugalError;->getStatusCode()I\n\n"
                "    move-result v0\n\n"
                "    invoke-static {v0}, Ljava/lang/String;->valueOf(I)Ljava/lang/String;\n\n"
                "    move-result-object v0\n\n"
                "    const-string v3, \"\"\n\n"
                "    invoke-direct {v2, v0, v3}, Lyf/a;-><init>(Ljava/lang/String;Ljava/lang/String;)V\n\n"
                "    invoke-direct {v1, v2}, LuP/a$a;-><init>(Ljava/lang/Object;)V\n\n"
                "    return-object v1\n\n"
                "    :cond_0\n"
            )
            if old_fail in text:
                text = text.replace(old_fail, new_fail)
                gp_repo.write_text(text, encoding="utf-8")

    load_pg = (
        PATCHED_DIR
        / "smali_classes3"
        / "es.2"
        / "bancosantander"
        / "apps"
        / "mobile"
        / "features"
        / "private_home"
        / "pg"
        / "BasePGPresenter$loadPGData$1.smali"
    )
    if load_pg.exists():
        text = load_pg.read_text(encoding="utf-8")
        old_fail_ui = (
            "    invoke-virtual {p1}, Les/bancosantander/apps/mobile/android/base/presenters/BasePresenter;->Bn()V\n\n"
            "    invoke-virtual {v0}, Ljava/lang/Throwable;->getMessage()Ljava/lang/String;\n\n"
            "    move-result-object v0\n\n"
            "    const-string v1, \"Critical\"\n\n"
            "    if-eqz v0, :cond_6\n\n"
            "    invoke-static {v0}, LAU/C;->p0(Ljava/lang/CharSequence;)Z\n\n"
            "    move-result v2\n\n"
            "    if-eqz v2, :cond_5\n\n"
            "    goto :goto_2\n\n"
            "    :cond_5\n"
            "    invoke-virtual {p1, v0, v1}, Les/bancosantander/apps/mobile/android/base/presenters/BasePresenter;->io(Ljava/lang/CharSequence;Ljava/lang/String;)V\n\n"
            "    goto :goto_3\n\n"
            "    :cond_6\n"
            "    :goto_2\n"
            "    sget v0, Lcom/santander/one/strings/R$string;->generic_error_internetConnection:I\n\n"
            "    invoke-virtual {p1, v0}, Landroidx/fragment/app/Fragment;->getString(I)Ljava/lang/String;\n\n"
            "    move-result-object v0\n\n"
            "    invoke-virtual {p1, v0, v1}, Les/bancosantander/apps/mobile/android/base/presenters/BasePresenter;->io(Ljava/lang/CharSequence;Ljava/lang/String;)V\n\n"
            "    :cond_7\n"
            "    :goto_3\n"
        )
        new_fail_ui = (
            "    invoke-virtual {p1}, Les/bancosantander/apps/mobile/features/private_home/pg/BasePGPresenter;->Fp()V\n\n"
            "    :cond_7\n"
            "    :goto_3\n"
        )
        if old_fail_ui in text:
            text = text.replace(old_fail_ui, new_fail_ui)
            load_pg.write_text(text, encoding="utf-8")

    print("  GP seed asset + session/BSAN fallback installed")


def patch_san_asset_aliases():
    """Copy bundled assets to alternate paths requested by microsite/CDN."""
    print("Patching SAN microsite asset aliases...")
    assets = PATCHED_DIR / "assets" / "default"
    copies = [
        (
            assets / "apps" / "SAN" / "offers" / "en_offersV4.xml",
            assets / "apps" / "SAN" / "en_offersV4.xml",
        ),
        (
            assets / "apps" / "SAN" / "offers" / "pt_offersV4.xml",
            assets / "apps" / "SAN" / "pt_offersV4.xml",
        ),
        (
            assets / "apps" / "newArq" / "android" / "en_app_config_v2.json",
            assets / "apps" / "SAN" / "en_app_config_v2.json",
        ),
        (
            assets / "apps" / "newArq" / "android" / "pt_app_config_v2.json",
            assets / "apps" / "SAN" / "pt_app_config_v2.json",
        ),
    ]
    for src, dst in copies:
        if src.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    print("  SAN asset aliases installed")


def patch_pg_shortcuts_trigger():
    """Guard ov() until GP wrapper exists; trigger fillView via ks() after load."""
    print("Patching GP dashboard crash guard + fillView trigger...")
    simple_pg = (
        PATCHED_DIR
        / "smali_classes10"
        / "com"
        / "santander"
        / "one"
        / "gp"
        / "legacy"
        / "ui"
        / "simple"
        / "SimplePGPresenter.smali"
    )
    if simple_pg.exists():
        text = simple_pg.read_text(encoding="utf-8")
        old_ov = (
            "    .end annotation\n\n"
            "    invoke-static {p0}, Landroidx/lifecycle/w;->a(Landroidx/lifecycle/v;)Landroidx/lifecycle/LifecycleCoroutineScope;\n"
        )
        new_ov = (
            "    .end annotation\n\n"
            "    invoke-virtual {p0}, Les/bancosantander/apps/mobile/features/private_home/pg/BasePGPresenter;->e8()Les/bancosantander/apps/domain/domain_objects/common/GlobalPositionWrapper;\n\n"
            "    move-result-object v0\n\n"
            "    if-nez v0, :cond_gp_ready\n\n"
            "    invoke-virtual {p0}, Landroidx/fragment/app/Fragment;->getContext()Landroid/content/Context;\n\n"
            "    move-result-object v0\n\n"
            "    if-nez v0, :cond_ov_ctx\n\n"
            "    invoke-static {}, Landroid/app/ActivityThread;->currentApplication()Landroid/app/Application;\n\n"
            "    move-result-object v0\n\n"
            "    :cond_ov_ctx\n"
            "    invoke-static {v0}, Lcom/azemon/santanderclone/GpSeed;->d(Landroid/content/Context;)Les/bancosantander/apps/domain/domain_objects/common/GlobalPositionWrapper;\n\n"
            "    move-result-object v0\n\n"
            "    if-eqz v0, :cond_ov_abort\n\n"
            "    invoke-virtual {p0, v0}, Les/bancosantander/apps/mobile/features/private_home/pg/BasePGPresenter;->Rs(Les/bancosantander/apps/domain/domain_objects/common/GlobalPositionWrapper;)V\n\n"
            "    goto :cond_gp_ready\n\n"
            "    :cond_ov_abort\n"
            "    iget-object v0, p0, Lcom/santander/one/gp/legacy/ui/simple/SimplePGPresenter;->Q7:Lcom/santander/one/gp/legacy/ui/simple/SimplePGView;\n\n"
            "    if-eqz v0, :cond_ov_done\n\n"
            "    invoke-virtual {v0}, Lcom/santander/one/gp/legacy/ui/simple/SimplePGView;->z0()V\n\n"
            "    :cond_ov_done\n"
            "    return-void\n\n"
            "    :cond_gp_ready\n"
            "    invoke-static {p0}, Landroidx/lifecycle/w;->a(Landroidx/lifecycle/v;)Landroidx/lifecycle/LifecycleCoroutineScope;\n"
        )
        if old_ov in text and ":cond_gp_ready" not in text:
            text = text.replace(old_ov, new_ov, 1)
        old_en = (
            "    :cond_0\n"
            "    return-void\n"
            ".end method\n\n"
            ".method public Eq()Z\n"
        )
        new_en = (
            "    :cond_0\n"
            "    invoke-static {p0}, Lcom/azemon/santanderclone/GpSeed;->c(Landroidx/fragment/app/Fragment;)V\n\n"
            "    return-void\n"
            ".end method\n\n"
            ".method public Eq()Z\n"
        )
        if old_en in text and "GpSeed;->c" not in text.split(".method public En()V")[1].split(".method public Eq()Z")[0]:
            text = text.replace(old_en, new_en, 1)
        if text != simple_pg.read_text(encoding="utf-8"):
            simple_pg.write_text(text, encoding="utf-8")

    load_pg = (
        PATCHED_DIR
        / "smali_classes3"
        / "es.2"
        / "bancosantander"
        / "apps"
        / "mobile"
        / "features"
        / "private_home"
        / "pg"
        / "BasePGPresenter$loadPGData$1.smali"
    )
    if load_pg.exists():
        text = load_pg.read_text(encoding="utf-8")
        for old, new in [
            (
                "    :goto_1\n"
                "    invoke-virtual {v0}, Les/bancosantander/apps/mobile/features/private_home/pg/BasePGPresenter;->Rr()V\n\n"
                "    invoke-virtual {v0}, Les/bancosantander/apps/mobile/features/private_home/pg/BasePGPresenter;->Fp()V\n\n"
                "    invoke-static {v0}, Lcom/azemon/santanderclone/GpSeed;->b(Landroidx/fragment/app/Fragment;)V\n",
                "    :goto_1\n"
                "    invoke-static {}, Ljava/util/Collections;->emptyList()Ljava/util/List;\n\n"
                "    move-result-object v1\n\n"
                "    invoke-virtual {v0, v1}, Les/bancosantander/apps/mobile/features/private_home/pg/BasePGPresenter;->ks(Ljava/util/List;)V\n\n"
                "    invoke-virtual {v0}, Les/bancosantander/apps/mobile/features/private_home/pg/BasePGPresenter;->Fp()V\n",
            ),
            (
                "    :goto_1\n"
                "    invoke-virtual {v0}, Les/bancosantander/apps/mobile/features/private_home/pg/BasePGPresenter;->Fp()V\n",
                "    :goto_1\n"
                "    invoke-static {}, Ljava/util/Collections;->emptyList()Ljava/util/List;\n\n"
                "    move-result-object v1\n\n"
                "    invoke-virtual {v0, v1}, Les/bancosantander/apps/mobile/features/private_home/pg/BasePGPresenter;->ks(Ljava/util/List;)V\n\n"
                "    invoke-virtual {v0}, Les/bancosantander/apps/mobile/features/private_home/pg/BasePGPresenter;->Fp()V\n",
            ),
            (
                "    invoke-virtual {v0}, Les/bancosantander/apps/mobile/features/private_home/pg/BasePGPresenter;->Fp()V\n\n"
                "    invoke-static {v0}, Lcom/azemon/santanderclone/GpSeed;->b(Landroidx/fragment/app/Fragment;)V\n\n"
                "    invoke-static {v0}, Les/bancosantander/apps/mobile/features/private_home/pg/BasePGPresenter;->lp(Les/bancosantander/apps/mobile/features/private_home/pg/BasePGPresenter;)V\n",
                "    invoke-virtual {v0}, Les/bancosantander/apps/mobile/features/private_home/pg/BasePGPresenter;->Fp()V\n\n"
                "    invoke-static {v0}, Lcom/azemon/santanderclone/GpSeed;->b(Landroidx/fragment/app/Fragment;)V\n\n"
                "    invoke-static {v0}, Les/bancosantander/apps/mobile/features/private_home/pg/BasePGPresenter;->lp(Les/bancosantander/apps/mobile/features/private_home/pg/BasePGPresenter;)V\n",
            ),
        ]:
            if old in text:
                text = text.replace(old, new)
                break
        old_fail_b = (
            "    invoke-virtual {p1}, Les/bancosantander/apps/mobile/features/private_home/pg/BasePGPresenter;->Fp()V\n\n"
            "    invoke-static {p1}, Lcom/azemon/santanderclone/GpSeed;->b(Landroidx/fragment/app/Fragment;)V\n\n"
            "    :cond_7\n"
        )
        new_fail = (
            "    invoke-virtual {p1}, Les/bancosantander/apps/mobile/features/private_home/pg/BasePGPresenter;->Fp()V\n\n"
            "    invoke-static {p1}, Lcom/azemon/santanderclone/GpSeed;->c(Landroidx/fragment/app/Fragment;)V\n\n"
            "    invoke-virtual {p1}, Les/bancosantander/apps/mobile/features/private_home/pg/BasePGPresenter;->Rr()V\n\n"
            "    :cond_7\n"
        )
        if old_fail_b in text:
            text = text.replace(old_fail_b, new_fail)
        else:
            old_fail = (
                "    invoke-virtual {p1}, Les/bancosantander/apps/mobile/features/private_home/pg/BasePGPresenter;->Fp()V\n\n"
                "    :cond_7\n"
            )
            if old_fail in text:
                text = text.replace(old_fail, new_fail)
        old_success = (
            "    :goto_1\n"
            "    invoke-static {}, Ljava/util/Collections;->emptyList()Ljava/util/List;\n\n"
            "    move-result-object v1\n\n"
            "    invoke-virtual {v0, v1}, Les/bancosantander/apps/mobile/features/private_home/pg/BasePGPresenter;->ks(Ljava/util/List;)V\n\n"
            "    invoke-virtual {v0}, Les/bancosantander/apps/mobile/features/private_home/pg/BasePGPresenter;->Fp()V\n"
        )
        new_success = (
            "    :goto_1\n"
            "    invoke-static {v0}, Lcom/azemon/santanderclone/GpSeed;->c(Landroidx/fragment/app/Fragment;)V\n\n"
            "    invoke-virtual {v0}, Les/bancosantander/apps/mobile/features/private_home/pg/BasePGPresenter;->Rr()V\n\n"
            "    invoke-virtual {v0}, Les/bancosantander/apps/mobile/features/private_home/pg/BasePGPresenter;->Fp()V\n"
        )
        if old_success in text and "GpSeed;->c" not in text.split(":goto_1")[1].split(":cond_4")[0]:
            text = text.replace(old_success, new_success)
        load_pg.write_text(text, encoding="utf-8")

    simple_pg_view = (
        PATCHED_DIR
        / "smali_classes10"
        / "com"
        / "santander"
        / "one"
        / "gp"
        / "legacy"
        / "ui"
        / "simple"
        / "SimplePGView.smali"
    )
    if simple_pg_view.exists():
        text = simple_pg_view.read_text(encoding="utf-8")
        old_z0 = (
            "    sget v0, Lcom/santander/one/legacy/R$id;->fake_pg:I\n\n"
            "    invoke-static {p0, v0}, LDR/b;->b(LGR/b;I)Landroid/view/View;\n\n"
            "    move-result-object v0\n\n"
            "    check-cast v0, Landroid/widget/FrameLayout;\n\n"
            "    const/16 v1, 0x8\n\n"
            "    invoke-virtual {v0, v1}, Landroid/view/View;->setVisibility(I)V\n\n"
            "    sget v0, Lcom/santander/one/gp/legacy/R$id;->simple_pg_coordinator_layout:I\n\n"
            "    invoke-static {p0, v0}, LDR/b;->b(LGR/b;I)Landroid/view/View;\n"
        )
        new_z0 = (
            "    sget v0, Lcom/santander/one/legacy/R$id;->fake_pg:I\n\n"
            "    invoke-static {p0, v0}, LDR/b;->b(LGR/b;I)Landroid/view/View;\n\n"
            "    move-result-object v0\n\n"
            "    if-eqz v0, :cond_skip_fake\n\n"
            "    const/16 v1, 0x8\n\n"
            "    invoke-virtual {v0, v1}, Landroid/view/View;->setVisibility(I)V\n\n"
            "    :cond_skip_fake\n"
            "    sget v0, Lcom/santander/one/gp/legacy/R$id;->simple_pg_coordinator_layout:I\n\n"
            "    invoke-static {p0, v0}, LDR/b;->b(LGR/b;I)Landroid/view/View;\n"
        )
        if old_z0 in text and ":cond_skip_fake" not in text:
            text = text.replace(old_z0, new_z0, 1)
        old_z0b = (
            "    move-result-object v0\n\n"
            "    check-cast v0, Lcom/santander/one/gp/legacy/ui/simple/SimplePgCoordinatorLayout;\n\n"
            "    const/4 v1, 0x0\n\n"
            "    invoke-virtual {v0, v1}, Landroidx/coordinatorlayout/widget/CoordinatorLayout;->setVisibility(I)V\n\n"
            "    return-void\n"
        )
        new_z0b = (
            "    move-result-object v0\n\n"
            "    if-eqz v0, :cond_skip_coord\n\n"
            "    check-cast v0, Lcom/santander/one/gp/legacy/ui/simple/SimplePgCoordinatorLayout;\n\n"
            "    const/4 v1, 0x0\n\n"
            "    invoke-virtual {v0, v1}, Landroidx/coordinatorlayout/widget/CoordinatorLayout;->setVisibility(I)V\n\n"
            "    :cond_skip_coord\n"
            "    return-void\n"
        )
        if old_z0b in text:
            text = text.replace(old_z0b, new_z0b, 1)
            simple_pg_view.write_text(text, encoding="utf-8")
    print("  GP dashboard crash guard installed")


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
        patch_smali_method(
            fragment,
            "public final Gn()V",
            """.method public final Gn()V
    .locals 0

    return-void
.end method""",
        )
    ui_effect = (
        PATCHED_DIR
        / "smali_classes12"
        / "com"
        / "santander"
        / "one"
        / "publicproducts"
        / "ui"
        / "feature"
        / "home"
        / "PublicProductsFragment$UI$2$1.smali"
    )
    if ui_effect.exists():
        text = ui_effect.read_text(encoding="utf-8")
        old = (
            "    invoke-virtual {p1}, Lcom/santander/one/publicproducts/ui/feature/home/PublicProductsViewModel$a;->d()Z\n\n"
            "    move-result p1\n\n"
            "    if-eqz p1, :cond_0\n\n"
            "    iget-object p1, p0, Lcom/santander/one/publicproducts/ui/feature/home/PublicProductsFragment$UI$2$1;->this$0:Lcom/santander/one/publicproducts/ui/feature/home/PublicProductsFragment;\n\n"
            "    invoke-static {p1}, Lcom/santander/one/publicproducts/ui/feature/home/PublicProductsFragment;->rn(Lcom/santander/one/publicproducts/ui/feature/home/PublicProductsFragment;)V\n\n"
            "    :cond_0"
        )
        if old in text:
            text = text.replace(old, "    goto :cond_0\n\n    :cond_0")
            ui_effect.write_text(text, encoding="utf-8")
    vm_state = (
        PATCHED_DIR
        / "smali_classes12"
        / "com"
        / "santander"
        / "one"
        / "publicproducts"
        / "ui"
        / "feature"
        / "home"
        / "PublicProductsViewModel$a.smali"
    )
    if vm_state.exists():
        patch_smali_method(
            vm_state,
            "public final d()Z",
            """.method public final d()Z
    .locals 1

    const/4 v0, 0x0

    return v0
.end method""",
        )
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


def patch_skip_onboarding():
    """Skip first-login onboarding and permission dialogs so login lands on dashboard."""
    print("Patching onboarding skip...")

    config_globs = [
        PATCHED_DIR / "assets" / "default" / "apps" / "newArq" / "android" / "en_app_config_v2.json",
        PATCHED_DIR / "assets" / "default" / "apps" / "newArq" / "android" / "pt_app_config_v2.json",
        PATCHED_DIR / "assets" / "default" / "apps" / "newArq" / "android" / "app_config_v2.json",
        PATCHED_DIR / "assets" / "default" / "apps" / "SAN" / "en_app_config_v2.json",
        PATCHED_DIR / "assets" / "default" / "apps" / "SAN" / "pt_app_config_v2.json",
    ]
    for cfg in config_globs:
        if cfg.exists():
            text = cfg.read_text(encoding="utf-8")
            text = text.replace('"disableOnboarding": "false"', '"disableOnboarding": "true"')
            text = text.replace('"disableOnboarding": false', '"disableOnboarding": true')
            cfg.write_text(text, encoding="utf-8")

    onboarding_gate = PATCHED_DIR / "smali_classes10" / "ho.1" / "b.smali"
    if onboarding_gate.exists():
        text = onboarding_gate.read_text(encoding="utf-8")
        text = text.replace(
            "    const/4 v1, 0x1\n\n"
            "    invoke-virtual {v0, v1}, Lcom/santander/one/data/feature/userprefs/dto/FirstLoginPrefsDTO;->setShowOnboarding(Z)V",
            "    const/4 v1, 0x0\n\n"
            "    invoke-virtual {v0, v1}, Lcom/santander/one/data/feature/userprefs/dto/FirstLoginPrefsDTO;->setShowOnboarding(Z)V",
        )
        onboarding_gate.write_text(text, encoding="utf-8")
        patch_smali_method(
            onboarding_gate,
            "public a()Z",
            """.method public a()Z
    .locals 1

    const/4 v0, 0x0

    return v0
.end method""",
        )

    first_login = (
        PATCHED_DIR
        / "smali_classes9"
        / "com"
        / "santander"
        / "one"
        / "data"
        / "feature"
        / "userprefs"
        / "dto"
        / "FirstLoginPrefsDTO.smali"
    )
    for method_sig, new_body in [
        (
            "public final getShowOnboarding()Z",
            """.method public final getShowOnboarding()Z
    .locals 1

    const/4 v0, 0x0

    return v0
.end method""",
        ),
        (
            "public final getShowNotificationsDialog()Z",
            """.method public final getShowNotificationsDialog()Z
    .locals 1

    const/4 v0, 0x0

    return v0
.end method""",
        ),
        (
            "public final getShowLocationDialog()Z",
            """.method public final getShowLocationDialog()Z
    .locals 1

    const/4 v0, 0x0

    return v0
.end method""",
        ),
    ]:
        patch_smali_method(first_login, method_sig, new_body)

    print("  Onboarding + notification/location prompts disabled")


def patch_critical_error_dialog():
    """Suppress blocking 'We are sorry' ErrorDialogFragment on startup failures."""
    print("Patching critical error dialog handler...")
    handler = PATCHED_DIR / "smali_classes9" / "com" / "santander" / "one" / "error" / "ui" / "handler" / "d.smali"
    if not handler.exists():
        return
    text = handler.read_text(encoding="utf-8")
    # Method h(): when no custom message is provided, show ErrorDialogFragment (:cond_0).
    old = (
        "    :cond_0\n"
        "    new-instance p2, Lcom/santander/one/error/ui/feature/dialog/view/ErrorDialogFragment;\n\n"
        "    invoke-direct {p2}, Lcom/santander/one/error/ui/feature/dialog/view/ErrorDialogFragment;-><init>()V\n\n"
        "    invoke-virtual {p2, p3}, Lcom/santander/one/error/ui/feature/dialog/view/ErrorDialogFragment;->An(LkT/a;)V\n\n"
        "    sget-object p3, LXS/p;->a:LXS/p;\n\n"
        "    invoke-virtual {p0, p1, p2}, Lcom/santander/one/error/ui/handler/d;->t(Landroidx/fragment/app/Fragment;Landroidx/fragment/app/DialogFragment;)V\n\n"
        "    return-void\n"
        ".end method\n\n"
        ".method public final n(LVc/u;)V"
    )
    new = (
        "    :cond_0\n"
        "    return-void\n"
        ".end method\n\n"
        ".method public final n(LVc/u;)V"
    )
    if old in text:
        text = text.replace(old, new)
        handler.write_text(text, encoding="utf-8")
        print("  Critical ErrorDialogFragment suppressed (handler.h)")
    else:
        print("  Warning: critical error dialog patch pattern not found")


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
    patched = patch_smali_method(
        context_wrapper,
        "public getSystemService(Ljava/lang/String;)Ljava/lang/Object;",
        """.method public getSystemService(Ljava/lang/String;)Ljava/lang/Object;
    .locals 1

    const-string v0, "layout_inflater"

    invoke-virtual {v0, p1}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result v0

    if-eqz v0, :cond_1

    iget-object p1, p0, Ll/d;->c:Landroid/view/LayoutInflater;

    if-nez p1, :cond_0

    invoke-virtual {p0}, Landroid/content/ContextWrapper;->getBaseContext()Landroid/content/Context;

    move-result-object p1

    invoke-static {p1}, Landroid/view/LayoutInflater;->from(Landroid/content/Context;)Landroid/view/LayoutInflater;

    move-result-object p1

    invoke-virtual {p1, p0}, Landroid/view/LayoutInflater;->cloneInContext(Landroid/content/Context;)Landroid/view/LayoutInflater;

    move-result-object p1

    iput-object p1, p0, Ll/d;->c:Landroid/view/LayoutInflater;

    :cond_0
    iget-object p1, p0, Ll/d;->c:Landroid/view/LayoutInflater;

    return-object p1

    :cond_1
    invoke-virtual {p0}, Landroid/content/ContextWrapper;->getBaseContext()Landroid/content/Context;

    move-result-object v0

    invoke-virtual {v0, p1}, Landroid/content/Context;->getSystemService(Ljava/lang/String;)Ljava/lang/Object;

    move-result-object p1

    return-object p1
.end method""",
    )
    if patched:
        print("  Patched AppCompat context wrapper (layout_inflater)")
    else:
        print("  WARNING: AppCompat context wrapper patch failed")


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
    patch_gp_seed_fallback()
    patch_san_asset_aliases()
    patch_pg_shortcuts_trigger()
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
    patch_skip_onboarding()
    patch_critical_error_dialog()
    patch_legacy_generic_error_dialog()
    patch_public_products_assets()
    patch_context_wrapper()
    patch_ssl_pinning()
    build_apk()
    sign_apk()
    print("\nDone! Install SantanderClone-signed.apk and start mock-server.")


if __name__ == "__main__":
    main()
