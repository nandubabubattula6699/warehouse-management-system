"""
Warehouse Label Small Language Model (WarehouseLabelSLM)
--------------------------------------------------------
A lightweight, trainable contextual token-sequence model trained directly on
Alexander Warehouse's catalog (styles, colors, sizes, pcs/box, quantities) plus
verified floor corrections.

Predicts BIO entity tags across OCR text:
  B-STYLE / I-STYLE   -> Product SKU / Style code (e.g. A12501, VDSW-2092 SND)
  B-COLOR / I-COLOR   -> Colorway (e.g. NATURAL WHITE, METALIC PINK, SAND)
  B-QTY               -> Total pieces / quantity (e.g. 15, 30, 48)
  B-PCS_BOX           -> Pieces per carton/box (e.g. 15, 24, 48)
  B-SIZE              -> Shoe/apparel size (e.g. 10.5, 8.5W, M, OS)
  O                   -> Distractors & metadata (PO#, Line/Sec/Lvl, weight, headers)
"""
from difflib import SequenceMatcher
import os
import pickle
import re
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

STYLE_KW = {"style", "sku", "item", "art", "article", "model", "code", "part", "ref", "st", "style#", "sku#"}
COLOR_KW = {"color", "colour", "col", "clr", "colorway", "shade"}
QTY_KW = {"qty", "quantity", "total", "units", "unit", "pcs", "pieces", "pc", "ea", "count", "prs", "pairs"}
BOX_KW = {"box", "boxes", "ctn", "ctns", "carton", "cartons", "case", "pack"}
SIZE_KW = {"size", "sz", "us", "eu", "uk", "wmns", "mens"}
LOC_KW = {"line", "ln", "row", "sec", "section", "lvl", "level", "shelf", "bin", "rack", "zone", "part"}
IGNORE_KW = {"po", "invoice", "inv", "gw", "nw", "gross", "net", "kg", "kgs", "lbs", "made", "of", "date", "lot"}

COLOR_ALIASES = {
    "BLK": "BLACK",
    "WHT": "WHITE",
    "NAT": "NATURAL",
    "NAT WHT": "NATURAL WHITE",
    "NAT WHITE": "NATURAL WHITE",
    "NAT BLK": "NATURAL BLACK",
    "NAT BLACK": "NATURAL BLACK",
    "NVY": "NAVY",
    "GRY": "GREY",
    "GRAY": "GREY",
    "SND": "SAND",
    "BRN": "BROWN",
    "PNK": "PINK",
    "YEL": "YELLOW",
    "BURG": "BURGUNDY",
    "LAV": "LAVENDER",
    "BLU": "BLUE",
    "GRN": "GREEN",
    "MET": "METALIC",
    "METALLIC PINK": "METALIC PINK",
    "METALLIC BROWN": "METALIC BROWN",
}

_OCR_SUBS = str.maketrans({"O": "0", "Q": "0", "D": "0", "I": "1", "L": "1", "|": "1", "S": "5", "B": "8", "Z": "2", "G": "6"})
_QTY_UNIT_SPLIT_RE = re.compile(r"\b(\d{1,5})(PCS|PC|PIECES|EA|UNITS|PRS|PAIRS|CTN|CTNS|BOX|BOXES)\b", re.IGNORECASE)
_KW_STICK_SPLIT_RE = re.compile(r"\b(STYLE|SKU|COLOR|COLOUR|QTY|SIZE)(?=[A-Z0-9]{2,})")
_TOKEN_RE = re.compile(r"[A-Za-z0-9]+(?:[-.][A-Za-z0-9]+)*|[:/|,#()]")


def ocr_skeleton(text: str) -> str:
    """Normalize common OCR digit/letter confusions for fuzzy SKU matching."""
    return re.sub(r"[^A-Z0-9]", "", (text or "").upper()).translate(_OCR_SUBS)


def _token_shape(tok: str) -> str:
    out = []
    for ch in tok[:14]:
        if ch.isupper():
            out.append("X")
        elif ch.islower():
            out.append("x")
        elif ch.isdigit():
            out.append("9")
        else:
            out.append(ch)
    return "".join(out)


def tokenize_document(text: str) -> List[Dict[str, Any]]:
    """
    Tokenize OCR text while keeping line index, line context, and splitting stuck units (e.g. 15PCS -> 15 PCS).
    """
    tokens: List[Dict[str, Any]] = []
    lines = (text or "").splitlines()
    for line_idx, raw_line in enumerate(lines):
        prepped = _KW_STICK_SPLIT_RE.sub(r"\1 ", raw_line.strip())
        prepped = _QTY_UNIT_SPLIT_RE.sub(r"\1 \2", prepped)
        raw_toks = _TOKEN_RE.findall(prepped)
        if not raw_toks:
            continue
        non_punct = [t for t in raw_toks if t not in {":", "/", "|", ",", "#", "(", ")"}]
        lower_words = {t.lower() for t in non_punct}
        for pos, tok in enumerate(raw_toks):
            tokens.append({
                "text": tok,
                "lower": tok.lower(),
                "upper": tok.upper(),
                "line_idx": line_idx,
                "pos": pos,
                "line_len": len(raw_toks),
                "line_words": lower_words,
                "line_text": raw_line,
            })
    return tokens


def _word_role(w: str) -> str:
    wl = w.lower()
    if wl in STYLE_KW:
        return "KW_STYLE"
    if wl in COLOR_KW:
        return "KW_COLOR"
    if wl in QTY_KW:
        return "KW_QTY"
    if wl in BOX_KW:
        return "KW_BOX"
    if wl in SIZE_KW:
        return "KW_SIZE"
    if wl in LOC_KW:
        return "KW_LOC"
    if wl in IGNORE_KW:
        return "KW_IGN"
    if wl in {":", "/", "|", ",", "#", "(", ")"}:
        return "PUNCT"
    return "WORD"


class WarehouseVocab:
    """Lookup tables built from warehouse inventory data."""

    def __init__(
        self,
        styles: List[dict],
        colors: List[str],
        sizes: List[str],
    ):
        self.style_records: Dict[str, dict] = {s["style"].upper(): s for s in styles if s.get("style")}
        self.styles: List[str] = sorted(self.style_records.keys())
        self.style_set = set(self.styles)
        self.style_skeletons: Dict[str, List[str]] = {}
        for st in self.styles:
            sk = ocr_skeleton(st)
            self.style_skeletons.setdefault(sk, []).append(st)
            # Also index first part of multi-token styles (e.g. VDSW-2092 from VDSW-2092 SND)
            first = st.split()[0]
            if first != st:
                self.style_skeletons.setdefault(ocr_skeleton(first), []).append(st)

        self.colors: List[str] = sorted({c.upper().strip() for c in colors if c and c.strip()})
        self.color_set = set(self.colors)
        self.color_words = set()
        for c in self.colors:
            for w in re.findall(r"[A-Za-z]+", c.lower()):
                if len(w) >= 2:
                    self.color_words.add(w)
        for alias_k, alias_v in COLOR_ALIASES.items():
            for w in alias_k.lower().split():
                self.color_words.add(w)
            for w in alias_v.lower().split():
                self.color_words.add(w)

        self.sizes = sorted({sz.upper().strip() for sz in sizes if sz and sz.strip()})
        self.size_set = set(self.sizes) | {"OS", "XS", "S", "M", "L", "XL", "XXL", "6", "6.5", "7", "7.5", "8", "8.5", "9", "9.5", "10", "10.5", "11", "11.5", "12", "12.5", "13", "14"}

    def match_style(self, candidate: str) -> Tuple[Optional[str], float]:
        if not candidate:
            return (None, 0.0)
        cand = re.sub(r"\s+", " ", candidate.strip().upper())
        if cand in self.style_set:
            return (cand, 1.0)

        sk = ocr_skeleton(cand)
        if sk in self.style_skeletons and len(sk) >= 4:
            matches = self.style_skeletons[sk]
            best = max(matches, key=lambda m: SequenceMatcher(None, cand, m).ratio())
            return (best, 0.96)

        best_style = None
        best_score = 0.0
        for st in self.styles:
            # Quick length filter
            if abs(len(st) - len(cand)) > 4:
                continue
            r_raw = SequenceMatcher(None, cand, st).ratio()
            r_sk = SequenceMatcher(None, sk, ocr_skeleton(st)).ratio()
            score = 0.45 * r_raw + 0.55 * r_sk
            if score > best_score:
                best_score = score
                best_style = st
        if best_score >= 0.80:
            return (best_style, round(best_score, 4))
        return (None, round(best_score, 4))

    def match_color(self, candidate: str) -> Tuple[Optional[str], float]:
        if not candidate:
            return (None, 0.0)
        cand = re.sub(r"\s+", " ", candidate.strip().upper())
        cand = COLOR_ALIASES.get(cand, cand)
        # Expand word-by-word aliases (e.g. "NAT WHT" or "MET PINK")
        words = cand.split()
        expanded = " ".join(COLOR_ALIASES.get(w, w) for w in words)
        if expanded in self.color_set:
            return (expanded, 1.0)
        if cand in self.color_set:
            return (cand, 1.0)

        best_col = None
        best_score = 0.0
        for col in self.colors:
            score = SequenceMatcher(None, expanded, col).ratio()
            if score > best_score:
                best_score = score
                best_col = col
        if best_score >= 0.78:
            return (best_col, round(best_score, 4))
        return (None, round(best_score, 4))


def _to_int32_csr(X):
    X = X.tocsr()
    if X.indices.dtype != np.int32:
        X.indices = X.indices.astype(np.int32, copy=False)
    if X.indptr.dtype != np.int32:
        X.indptr = X.indptr.astype(np.int32, copy=False)
    return X


class WarehouseLabelSLM:
    """
    Trained contextual sequence tagger + warehouse catalog matcher.
    """

    def __init__(self, vectorizer, classifier, vocab: WarehouseVocab, metadata: Optional[dict] = None):
        self.vectorizer = vectorizer
        self.classifier = classifier
        self.vocab = vocab
        self.metadata = metadata or {}

    def _non_punct_neighbor(self, tokens: List[Dict[str, Any]], idx: int, step: int) -> Optional[Dict[str, Any]]:
        j = idx + step
        while 0 <= j < len(tokens):
            if tokens[j]["text"] not in {":", "/", "|", ",", "#", "(", ")"}:
                return tokens[j]
            j += step
        return None

    def extract_token_features(self, tokens: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        # Map line_idx -> list of keywords in that line
        line_kw_map: Dict[int, set] = {}
        for t in tokens:
            line_kw_map[t["line_idx"]] = t["line_words"]

        feats_list: List[Dict[str, Any]] = []
        for i, t in enumerate(tokens):
            w = t["text"]
            wl = t["lower"]
            wu = t["upper"]
            li = t["line_idx"]
            lw = t["line_words"]
            prev_lw = line_kw_map.get(li - 1, set())

            is_int = w.isdigit()
            is_float = bool(re.fullmatch(r"\d+\.\d+", w))
            has_alpha = any(c.isalpha() for c in w)
            has_digit = any(c.isdigit() for c in w)
            sk = ocr_skeleton(w)

            in_style_exact = wu in self.vocab.style_set or (sk in self.vocab.style_skeletons and len(sk) >= 5 and has_alpha)
            in_color_word = wl in self.vocab.color_words and has_alpha and _word_role(wl) == "WORD"
            in_size_vocab = wu in self.vocab.size_set

            f: Dict[str, Any] = {
                "bias": 1.0,
                "lower": wl if len(wl) <= 18 else wl[:18],
                "shape": _token_shape(w),
                "role": _word_role(wl),
                "is_int": is_int,
                "is_float": is_float,
                "has_alpha": has_alpha,
                "has_digit": has_digit,
                "is_alnum_mix": has_alpha and has_digit,
                "has_hyphen": "-" in w,
                "len": min(len(w), 16),
                "pref2": wl[:2],
                "pref3": wl[:3],
                "suff2": wl[-2:],
                "suff3": wl[-3:],
                "starts_brand_prefix": wu.startswith(("A1", "A2", "TB", "TR", "VD", "VO", "EH", "WR", "TS", "TA")),
                "in_style_vocab": in_style_exact,
                "in_color_word": in_color_word,
                "in_size_vocab": in_size_vocab,
                "pos_0": t["pos"] == 0,
                "line_kw_style": bool(lw & STYLE_KW),
                "line_kw_color": bool(lw & COLOR_KW),
                "line_kw_qty": bool(lw & QTY_KW),
                "line_kw_box": bool(lw & BOX_KW),
                "line_kw_size": bool(lw & SIZE_KW),
                "line_kw_loc": bool(lw & LOC_KW),
                "line_kw_ign": bool(lw & IGNORE_KW),
                "prevline_kw_style": bool(prev_lw & STYLE_KW) and t["pos"] <= 1,
                "prevline_kw_color": bool(prev_lw & COLOR_KW) and t["pos"] <= 1,
                "prevline_kw_qty": bool(prev_lw & QTY_KW) and t["pos"] <= 1,
                "prevline_kw_box": bool(prev_lw & BOX_KW) and t["pos"] <= 1,
                "prevline_kw_size": bool(prev_lw & SIZE_KW) and t["pos"] <= 1,
            }

            if is_int:
                num_val = int(w)
                f["int_small_shoe"] = (4 <= num_val <= 15)
                f["int_box_common"] = num_val in {6, 8, 10, 12, 14, 15, 20, 24, 30, 36, 40, 45, 48, 60}
                f["int_large"] = (num_val > 100)

            for offset, name in [(-2, "m2"), (-1, "m1"), (1, "p1"), (2, "p2")]:
                j = i + offset
                if 0 <= j < len(tokens) and tokens[j]["line_idx"] == li:
                    nt = tokens[j]
                    f[f"{name}_lower"] = nt["lower"][:14]
                    f[f"{name}_role"] = _word_role(nt["lower"])
                    f[f"{name}_shape"] = _token_shape(nt["text"])
                    f[f"{name}_alnum_mix"] = any(c.isalpha() for c in nt["text"]) and any(c.isdigit() for c in nt["text"])
                else:
                    f[f"{name}_bound"] = True

            # Non-punctuation left & right neighbors (crucial when ":" or "/" sits between keyword and value)
            lnp = self._non_punct_neighbor(tokens, i, -1)
            if lnp:
                f["lnp_lower"] = lnp["lower"][:14]
                f["lnp_role"] = _word_role(lnp["lower"])
                f["lnp_same_line"] = (lnp["line_idx"] == li)
            rnp = self._non_punct_neighbor(tokens, i, 1)
            if rnp:
                f["rnp_lower"] = rnp["lower"][:14]
                f["rnp_role"] = _word_role(rnp["lower"])
                f["rnp_same_line"] = (rnp["line_idx"] == li)

            feats_list.append(f)
        return feats_list

    def predict(self, text: str) -> Dict[str, Any]:
        tokens = tokenize_document(text)
        if not tokens:
            return {
                "style": None,
                "matched_style": None,
                "style_confidence": 0.0,
                "color": None,
                "matched_color": None,
                "color_confidence": 0.0,
                "quantity": None,
                "quantity_confidence": 0.0,
                "pcs_per_box": None,
                "size": None,
                "brand": None,
                "catalog_verified": False,
                "tagged_tokens": [],
            }

        feats = self.extract_token_features(tokens)
        X = _to_int32_csr(self.vectorizer.transform(feats))
        probs = self.classifier.predict_proba(X)
        classes = list(self.classifier.classes_)
        pred_indices = np.argmax(probs, axis=1)

        tagged = []
        for idx, t in enumerate(tokens):
            tag = str(classes[pred_indices[idx]])
            conf = float(probs[idx, pred_indices[idx]])
            tagged.append({
                "text": t["text"],
                "line_idx": t["line_idx"],
                "tag": tag,
                "confidence": round(conf, 4),
            })

        # Extract contiguous BIO spans per entity
        spans: Dict[str, List[Tuple[str, float]]] = {
            "STYLE": [],
            "COLOR": [],
            "QTY": [],
            "PCS_BOX": [],
            "SIZE": [],
        }

        i = 0
        while i < len(tagged):
            tag = tagged[i]["tag"]
            if tag == "O":
                i += 1
                continue
            ent = tag.split("-", 1)[1] if "-" in tag else tag
            cur_line = tagged[i]["line_idx"]
            words = [tagged[i]["text"]]
            confs = [tagged[i]["confidence"]]
            j = i + 1
            while j < len(tagged):
                ntag = tagged[j]["tag"]
                nent = ntag.split("-", 1)[1] if "-" in ntag else ntag
                if nent == ent and tagged[j]["line_idx"] == cur_line and (ntag.startswith("I-") or ent in {"COLOR", "STYLE"}):
                    words.append(tagged[j]["text"])
                    confs.append(tagged[j]["confidence"])
                    j += 1
                else:
                    break
            phrase = " ".join(words).strip()
            phrase = re.sub(r"\s*([,/])\s*", r"\1", phrase)
            avg_conf = sum(confs) / len(confs)
            if ent in spans and phrase:
                spans[ent].append((phrase, avg_conf))
            i = j

        # Pick best span for each entity
        raw_style, style_conf = (max(spans["STYLE"], key=lambda x: x[1]) if spans["STYLE"] else (None, 0.0))
        raw_color, color_conf = (max(spans["COLOR"], key=lambda x: x[1]) if spans["COLOR"] else (None, 0.0))
        raw_size, size_conf = (max(spans["SIZE"], key=lambda x: x[1]) if spans["SIZE"] else (None, 0.0))

        # Catalog fallback if STYLE was not picked up strongly by sequence model
        matched_style, match_st_score = self.vocab.match_style(raw_style or "")
        if not matched_style:
            for t in tokens:
                if any(c.isalpha() for c in t["text"]) and any(c.isdigit() for c in t["text"]) and len(t["text"]) >= 5:
                    cand_m, cand_s = self.vocab.match_style(t["text"])
                    if cand_m and cand_s >= 0.88:
                        matched_style, match_st_score = cand_m, cand_s
                        if not raw_style:
                            raw_style, style_conf = t["text"], cand_s
                        break

        # Also check 2-token style (e.g. "VDSW-2092" + "SND")
        if raw_style and not matched_style and " " not in raw_style:
            # check if a warehouse style starts with raw_style
            ru = raw_style.upper()
            for st in self.vocab.styles:
                if st.startswith(ru + " "):
                    matched_style, match_st_score = st, 0.90
                    break

        final_style = matched_style or (raw_style.upper() if raw_style else None)
        final_style_conf = round(max(style_conf, match_st_score) if final_style else 0.0, 4)

        # Color repair & fallback
        matched_color, match_col_score = self.vocab.match_color(raw_color or "")
        if not matched_color and not raw_color:
            # Scan token pairs / singles against warehouse colors (avoiding keywords)
            upper_line = re.sub(r"\s+", " ", (text or "").upper())
            for col in sorted(self.vocab.colors, key=len, reverse=True):
                if len(col) >= 4 and re.search(rf"\b{re.escape(col)}\b", upper_line):
                    matched_color, match_col_score = col, 0.92
                    raw_color = col
                    break

        final_color = matched_color or (raw_color.upper() if raw_color else None)
        final_color_conf = round(max(color_conf, match_col_score) if final_color else 0.0, 4)

        # Quantity & Pcs/Box parsing
        qty_val = None
        qty_conf = 0.0
        for q_str, q_c in sorted(spans["QTY"], key=lambda x: x[1], reverse=True):
            m = re.search(r"\d+", q_str)
            if m:
                qty_val = int(m.group(0))
                qty_conf = round(q_c, 4)
                break

        pcs_box_val = None
        for p_str, _ in sorted(spans["PCS_BOX"], key=lambda x: x[1], reverse=True):
            m = re.search(r"\d+", p_str)
            if m:
                pcs_box_val = int(m.group(0))
                break

        # If sticker only lists PCS/BOX (common on full carton), total pieces == pcs_per_box unless QTY also given
        if qty_val is None and pcs_box_val is not None:
            qty_val = pcs_box_val
            qty_conf = 0.82

        # Brand inference from style or text
        brand = None
        if final_style and final_style in self.vocab.style_records:
            brand = self.vocab.style_records[final_style].get("brand")
        if not brand and final_style:
            su = final_style.upper()
            if su.startswith("VD"):
                brand = "VON DUTCH"
            elif su.startswith(("VO", "V-", "VAL")):
                brand = "VALENTINO"
            elif su.startswith("EH"):
                brand = "ED HARDY"
            else:
                brand = "ALLBIRDS"
        if not brand:
            tu = (text or "").upper()
            for bname in ("ALLBIRDS", "VON DUTCH", "VALENTINO", "ED HARDY"):
                if bname in tu:
                    brand = bname
                    break

        return {
            "style": final_style,
            "raw_style": raw_style.upper() if raw_style else None,
            "style_confidence": final_style_conf,
            "color": final_color,
            "raw_color": raw_color.upper() if raw_color else None,
            "color_confidence": final_color_conf,
            "quantity": qty_val,
            "quantity_confidence": qty_conf,
            "pcs_per_box": pcs_box_val,
            "size": raw_size.upper() if raw_size else None,
            "brand": brand,
            "catalog_verified": bool(matched_style),
            "tagged_tokens": tagged,
        }

    def save(self, path: str):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump(self, f, protocol=pickle.HIGHEST_PROTOCOL)

    @classmethod
    def load(cls, path: str) -> "WarehouseLabelSLM":
        with open(path, "rb") as f:
            return pickle.load(f)
