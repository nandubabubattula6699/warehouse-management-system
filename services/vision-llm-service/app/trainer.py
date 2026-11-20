"""
Warehouse SLM Training Pipeline
-------------------------------
Generates a rich synthetic + feedback-augmented training dataset directly from
Alexander Warehouse's live inventory catalog (styles, colors, sizes, pcs/box, brands)
plus real worker photo corrections saved in feedback.jsonl.

Trains and validates the WarehouseLabelSLM sequence model and saves the trained
model + accuracy report to models/.
"""
from datetime import datetime, timezone
import json
import os
import random
import re
import time
from typing import List, Optional, Tuple

from sklearn.feature_extraction import DictVectorizer
from sklearn.linear_model import SGDClassifier
from sklearn.metrics import classification_report, accuracy_score

from app.catalog_client import fetch_live_catalog_sync
from app.config import CATALOG_PATH, FEEDBACK_PATH, MODEL_PATH, REPORT_PATH
from app.slm_model import WarehouseLabelSLM, WarehouseVocab, _to_int32_csr, tokenize_document


def _corrupt_ocr(text: str, rng: random.Random) -> str:
    """Inject realistic camera OCR noise (0/O, 1/I/l, 5/S, 8/B) for robustness."""
    swaps = {"0": "O", "O": "0", "1": "I", "I": "1", "5": "S", "8": "B"}
    chars = list(text)
    for i, ch in enumerate(chars):
        if ch.upper() in swaps and rng.random() < 0.08:
            chars[i] = swaps[ch.upper()]
    return "".join(chars)


def _abbreviate_color(col: str, rng: random.Random) -> str:
    rep = {"NATURAL": "NAT", "WHITE": "WHT", "BLACK": "BLK", "BROWN": "BRN", "SAND": "SND", "PINK": "PNK", "NAVY": "NVY", "YELLOW": "YEL", "METALIC": "MET"}
    if rng.random() < 0.28:
        return " ".join(rep.get(w, w) for w in col.split())
    return col


def _label_synthetic_doc(
    lines: List[Tuple[str, Optional[str], Optional[str]]],
) -> Tuple[str, List[str]]:
    """
    Build document text and aligned BIO tags.
    Each tuple in `lines` is (text_line, target_ent_or_None, target_value_substring_or_None).
    """
    full_text = "\n".join(ln[0] for ln in lines)
    tokens = tokenize_document(full_text)
    tags = ["O"] * len(tokens)

    # Map line_idx -> entity spans
    for line_idx, (line_str, ent, target_val) in enumerate(lines):
        if not ent or not target_val:
            continue
        val_toks = [t["upper"] for t in tokenize_document(target_val)]
        if not val_toks:
            continue
        line_tok_indices = [idx for idx, tk in enumerate(tokens) if tk["line_idx"] == line_idx]
        for start_pos in range(len(line_tok_indices) - len(val_toks) + 1):
            window = line_tok_indices[start_pos:start_pos + len(val_toks)]
            if [tokens[w]["upper"] for w in window] == val_toks:
                tags[window[0]] = f"B-{ent}"
                for w in window[1:]:
                    tags[w] = f"I-{ent}"
                break

    return full_text, tags


def _generate_synthetic_sample(
    style: str,
    brand: str,
    color: str,
    size: str,
    qty: int,
    pcs_box: int,
    rng: random.Random,
    noisy: bool = True,
) -> Tuple[str, List[str]]:
    st_txt = _corrupt_ocr(style, rng) if (noisy and rng.random() < 0.25) else style
    col_base = _abbreviate_color(color, rng)
    col_txt = _corrupt_ocr(col_base, rng) if (noisy and rng.random() < 0.20) else col_base
    qty_str = str(qty)
    pcs_str = str(pcs_box)
    sz_str = size

    line_no = str(rng.randint(1, 14))
    sec_no = str(rng.randint(1, 36))
    lvl_no = str(rng.randint(1, 4))
    po_no = f"45{rng.randint(100000, 999999)}"
    ctn_no = f"{rng.randint(1, 24)} OF {rng.randint(25, 60)}"

    template_id = rng.randint(0, 7)
    rows: List[Tuple[str, Optional[str], Optional[str]]] = []

    if template_id == 0:
        # Standard shoe box / carton sticker with colons
        st_kw = rng.choice(["STYLE:", "SKU:", "STYLE NO:", "ITEM:"])
        col_kw = rng.choice(["COLOR:", "COLOUR:", "COL:", "CLR:"])
        qty_kw = rng.choice(["QTY:", "TOTAL QTY:", "PIECES:", "QUANTITY:"])
        rows = [
            (brand, None, None),
            (f"{st_kw} {st_txt}", "STYLE", st_txt),
            (f"{col_kw} {col_txt}", "COLOR", col_txt),
            (f"SIZE: {rng.choice(['', 'US '])}{sz_str}", "SIZE", sz_str),
            (f"{qty_kw} {qty_str} {rng.choice(['PCS', 'PIECES', 'UNITS', ''])}".strip(), "QTY", qty_str),
            (f"PCS/BOX: {pcs_str}", "PCS_BOX", pcs_str),
            (f"PO# {po_no}  LINE {line_no} SEC {sec_no} LVL {lvl_no}", None, None),
        ]
    elif template_id == 1:
        # Stacked multi-line header above value (common when OCR reads grid boxes)
        rows = [
            ("STYLE", None, None),
            (st_txt, "STYLE", st_txt),
            ("COLOR", None, None),
            (col_txt, "COLOR", col_txt),
            ("SIZE", None, None),
            (sz_str, "SIZE", sz_str),
            ("QTY", None, None),
            (f"{qty_str} PCS", "QTY", qty_str),
        ]
    elif template_id == 2:
        # Compact box end label (no colons)
        rows = [
            (f"{rng.choice(['SKU', 'STYLE'])} {st_txt}", "STYLE", st_txt),
            (f"{rng.choice(['COLOR', 'COL'])} {col_txt}", "COLOR", col_txt),
            (f"SZ {sz_str}", "SIZE", sz_str),
            (f"{qty_str} PCS", "QTY", qty_str),
            (f"PCS/CTN {pcs_str}", "PCS_BOX", pcs_str),
            (f"CTN {ctn_no}", None, None),
        ]
    elif template_id == 3:
        # Master carton shipping mark with G.W / N.W distractors
        rows = [
            (f"{brand} WAREHOUSE", None, None),
            (f"ART# {st_txt}", "STYLE", st_txt),
            (f"CLR: {col_txt}", "COLOR", col_txt),
            (f"PCS/CTN: {pcs_str}", "PCS_BOX", pcs_str),
            (f"TOTAL: {qty_str} PCS", "QTY", qty_str),
            (f"SIZE: {sz_str}", "SIZE", sz_str),
            (f"G.W: {rng.randint(8, 22)}.5 KGS  N.W: {rng.randint(7, 20)}.0 KGS", None, None),
            ("MADE IN VIETNAM", None, None),
        ]
    elif template_id == 4:
        # Stuck punctuation (OCR misses spaces after colons / before units)
        rows = [
            (f"STYLE:{st_txt}", "STYLE", st_txt),
            (f"COLOR:{col_txt}", "COLOR", col_txt),
            (f"SIZE:{sz_str}", "SIZE", sz_str),
            (f"QTY:{qty_str}PCS", "QTY", qty_str),
            (f"BOX {rng.randint(1, 12)} ROW {line_no} SEC {sec_no}", None, None),
        ]
    elif template_id == 5:
        # Minimalist label with location noise (with size)
        rows = [
            (f"MODEL: {st_txt}", "STYLE", st_txt),
            (f"COLOR: {col_txt}", "COLOR", col_txt),
            (f"SIZE: {sz_str}", "SIZE", sz_str),
            (f"QTY: {qty_str} PIECES", "QTY", qty_str),
            (f"LINE {line_no} SEC {sec_no} LVL {lvl_no}", None, None),
        ]
    elif template_id == 6:
        # Keyword-free shoe box sticker (no STYLE:/COLOR: prefixes)
        rows = [
            (brand, None, None),
            (st_txt, "STYLE", st_txt),
            (col_txt, "COLOR", col_txt),
            (f"US {sz_str}", "SIZE", sz_str),
            (f"{qty_str} PCS", "QTY", qty_str),
        ]
    else:
        # Multi-item or single-line sticker without prefixes
        rows = [
            (f"{st_txt}", "STYLE", st_txt),
            (f"{col_txt}", "COLOR", col_txt),
            (f"SIZE {sz_str}", "SIZE", sz_str),
            (f"{qty_str} PCS / {pcs_str} PER BOX", "QTY", qty_str),
        ]

    return _label_synthetic_doc(rows)


def _load_feedback_samples() -> List[Tuple[str, List[str]]]:
    samples: List[Tuple[str, List[str]]] = []
    if not os.path.exists(FEEDBACK_PATH):
        return samples
    with open(FEEDBACK_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            raw_text = rec.get("raw_text") or ""
            if not raw_text.strip():
                continue
            tokens = tokenize_document(raw_text)
            if not tokens:
                continue
            tags = ["O"] * len(tokens)
            for ent, val in [
                ("STYLE", rec.get("style")),
                ("COLOR", rec.get("color")),
                ("SIZE", rec.get("size")),
                ("QTY", str(rec["quantity"]) if rec.get("quantity") is not None else None),
                ("PCS_BOX", str(rec["pcs_per_box"]) if rec.get("pcs_per_box") is not None else None),
            ]:
                if not val:
                    continue
                val_toks = [t["upper"] for t in tokenize_document(str(val))]
                if not val_toks:
                    continue
                for start in range(len(tokens) - len(val_toks) + 1):
                    if [tokens[k]["upper"] for k in range(start, start + len(val_toks))] == val_toks and tags[start] == "O":
                        tags[start] = f"B-{ent}"
                        for k in range(start + 1, start + len(val_toks)):
                            tags[k] = f"I-{ent}"
                        break
            # Upweight real worker feedback by repeating 6x
            for _ in range(6):
                samples.append((raw_text, tags))
    return samples


def load_merged_catalog() -> dict:
    base = {"styles": [], "colors": [], "sizes": [], "common_pcs_per_box": [12, 15, 24, 48], "common_quantities": [15, 30, 45, 20, 48]}
    if os.path.exists(CATALOG_PATH):
        with open(CATALOG_PATH, encoding="utf-8") as f:
            base = json.load(f)

    live = fetch_live_catalog_sync()
    if live and live.get("styles"):
        by_style = {s["style"].upper(): s for s in base.get("styles", []) if s.get("style")}
        for s in live["styles"]:
            su = s["style"].upper()
            if su in by_style:
                by_style[su]["colors"] = sorted(set(by_style[su].get("colors", [])) | set(s.get("colors", [])))
                by_style[su]["sizes"] = sorted(set(by_style[su].get("sizes", [])) | set(s.get("sizes", [])))
                by_style[su]["pcs_per_box"] = sorted(set(by_style[su].get("pcs_per_box", [])) | set(s.get("pcs_per_box", [])))
            else:
                by_style[su] = s
        base["styles"] = sorted(by_style.values(), key=lambda x: x["style"])
        base["colors"] = sorted(set(base.get("colors", [])) | set(live.get("colors", [])))
        base["sizes"] = sorted(set(base.get("sizes", [])) | set(live.get("sizes", [])))
    return base


def train_warehouse_slm(samples_per_epoch: int = 7500, seed: int = 42) -> dict:
    """
    Generate training corpus from warehouse catalog + human feedback, train WarehouseLabelSLM,
    evaluate on held-out styles & labels, and persist weights + metrics report.
    """
    t0 = time.time()
    rng = random.Random(seed)
    catalog = load_merged_catalog()
    styles_list = catalog.get("styles", [])
    colors_list = catalog.get("colors", []) or ["NATURAL WHITE", "BLACK", "SAND", "BLIZZARD"]
    sizes_list = catalog.get("sizes", []) or ["8", "9", "9.5", "10", "10.5", "11", "M", "L", "OS"]
    common_pcs = catalog.get("common_pcs_per_box", []) or [12, 15, 20, 24, 48]
    common_qty = catalog.get("common_quantities", []) or [10, 15, 24, 30, 45, 48]

    vocab = WarehouseVocab(styles=styles_list, colors=colors_list, sizes=sizes_list)

    # Split styles 85% train / 15% validation so validation tests unseen styles too!
    shuffled_styles = list(styles_list)
    rng.shuffle(shuffled_styles)
    split_idx = max(1, int(len(shuffled_styles) * 0.85))
    train_styles = shuffled_styles[:split_idx]
    val_styles = shuffled_styles[split_idx:] or shuffled_styles[:50]

    # Also synthesize unseen future SKUs so the model never relies only on memorized SKUs
    unseen_val_styles = [
        {"style": f"A{rng.randint(15000, 99999)}", "brand": "ALLBIRDS", "colors": [], "sizes": [], "pcs_per_box": []}
        for _ in range(80)
    ] + [
        {"style": f"VDSW-{rng.randint(3000, 9999)} {rng.choice(['BLK', 'SND', 'WHT'])}", "brand": "VON DUTCH", "colors": [], "sizes": [], "pcs_per_box": []}
        for _ in range(40)
    ]

    def build_docs(style_pool: List[dict], n_docs: int) -> List[Tuple[str, List[str]]]:
        docs = []
        for _ in range(n_docs):
            s_rec = rng.choice(style_pool)
            st = s_rec["style"]
            br = s_rec.get("brand") or "ALLBIRDS"
            col = rng.choice(s_rec["colors"]) if s_rec.get("colors") else rng.choice(colors_list)
            sz = rng.choice(s_rec["sizes"]) if s_rec.get("sizes") else rng.choice(sizes_list)
            pcs = rng.choice(s_rec["pcs_per_box"]) if s_rec.get("pcs_per_box") else rng.choice(common_pcs)
            qty = pcs * rng.randint(1, 4) if rng.random() < 0.6 else rng.choice(common_qty)
            docs.append(_generate_synthetic_sample(st, br, col, sz, qty, pcs, rng))
        return docs

    train_docs = build_docs(train_styles, int(samples_per_epoch * 0.85))
    # Include feedback samples in training
    feedback_docs = _load_feedback_samples()
    train_docs.extend(feedback_docs)
    val_docs = build_docs(val_styles + unseen_val_styles, int(samples_per_epoch * 0.15))

    # Build temporary SLM for feature extraction
    vec = DictVectorizer(sparse=True)
    clf = SGDClassifier(loss="log_loss", alpha=1e-4, max_iter=35, tol=1e-4, random_state=seed, n_jobs=-1)
    temp_slm = WarehouseLabelSLM(vec, clf, vocab)

    def featurize(docs: List[Tuple[str, List[str]]]):
        all_X = []
        all_y = []
        for doc_text, doc_tags in docs:
            toks = tokenize_document(doc_text)
            if len(toks) != len(doc_tags):
                continue
            feats = temp_slm.extract_token_features(toks)
            all_X.extend(feats)
            all_y.extend(doc_tags)
        return all_X, all_y

    X_train_dicts, y_train = featurize(train_docs)
    X_val_dicts, y_val = featurize(val_docs)

    X_train = _to_int32_csr(vec.fit_transform(X_train_dicts))
    X_val = _to_int32_csr(vec.transform(X_val_dicts))
    clf.fit(X_train, y_train)

    y_pred = clf.predict(X_val)
    val_acc = float(accuracy_score(y_val, y_pred))
    cls_rep = classification_report(y_val, y_pred, output_dict=True, zero_division=0)

    # End-to-end document extraction check on 200 fresh rendered label docs (known catalog with noisy OCR + unseen clean SKUs)
    doc_hits = {"style": 0, "color": 0, "quantity": 0, "size": 0, "total": 200}
    slm = WarehouseLabelSLM(vec, clf, vocab)
    for idx in range(200):
        is_unseen = idx >= 150
        s_rec = rng.choice(unseen_val_styles if is_unseen else val_styles)
        st = s_rec["style"]
        br = s_rec.get("brand") or "ALLBIRDS"
        col = rng.choice(s_rec["colors"]) if s_rec.get("colors") else rng.choice(colors_list)
        sz = rng.choice(s_rec["sizes"]) if s_rec.get("sizes") else rng.choice(sizes_list)
        pcs = rng.choice(s_rec["pcs_per_box"]) if s_rec.get("pcs_per_box") else rng.choice(common_pcs)
        qty = pcs * rng.randint(1, 3)
        doc_text, _ = _generate_synthetic_sample(st, br, col, sz, qty, pcs, rng, noisy=(not is_unseen))
        out = slm.predict(doc_text)
        if out["style"] == st or out["raw_style"] == st:
            doc_hits["style"] += 1
        if out["color"] and (out["color"] == col or col in out["color"] or out["color"] in col):
            doc_hits["color"] += 1
        if out["quantity"] == qty:
            doc_hits["quantity"] += 1
        if out["size"] and re.sub(r"\s+", "", out["size"]) == re.sub(r"\s+", "", sz):
            doc_hits["size"] += 1

    elapsed = round(time.time() - t0, 2)
    report = {
        "model_name": "Alexander Warehouse Vision SLM v1 (RapidOCR + Contextual BIO Sequence Tagger)",
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "training_seconds": elapsed,
        "catalog_styles_count": len(styles_list),
        "catalog_colors_count": len(colors_list),
        "catalog_sizes_count": len(sizes_list),
        "feedback_samples_used": len(feedback_docs),
        "train_documents": len(train_docs),
        "train_tokens": len(y_train),
        "validation_documents": len(val_docs),
        "validation_tokens": len(y_val),
        "vocabulary_features": len(vec.feature_names_),
        "token_validation_accuracy": round(val_acc, 4),
        "macro_f1": round(float(cls_rep.get("macro avg", {}).get("f1-score", 0.0)), 4),
        "e2e_field_accuracy": {
            "style": round(doc_hits["style"] / 200.0, 4),
            "color": round(doc_hits["color"] / 200.0, 4),
            "quantity": round(doc_hits["quantity"] / 200.0, 4),
            "size": round(doc_hits["size"] / 200.0, 4),
        },
    }
    slm.metadata = report
    slm.save(MODEL_PATH)
    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    return report


if __name__ == "__main__":
    rep = train_warehouse_slm()
    print(json.dumps(rep, indent=2))
