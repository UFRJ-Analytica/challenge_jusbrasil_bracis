
from __future__ import annotations

import argparse
import json
import csv
import re
import sqlite3
import unicodedata
from collections import defaultdict
from pathlib import Path


UF_RE = re.compile(
    r"(?i)(?:/|-|\(|\s)(?:AC|AL|AP|AM|BA|CE|DF|ES|GO|MA|MT|MS|MG|PA|PB|PR|PE|PI|RJ|RN|RS|RO|RR|SC|SP|SE|TO)\b"
)

OCR_MAP = str.maketrans({
    "O": "0", "o": "0",
    "l": "1", "I": "1",
    "S": "5", "s": "5",
    "G": "6", "g": "69",  # g pode representar 6 ou 9 no ruido OCR
})

LAW_SOURCE_MAP = {
    "cpc": ("law", "13105"),
    "codigo de processo civil": ("law", "13105"),
    "cpp": ("law", "3689"),
    "codigo de processo penal": ("law", "3689"),
    "clt": ("law", "5452"),
    "consolidacao das leis do trabalho": ("law", "5452"),
    "cdc": ("law", "8078"),
    "codigo de defesa do consumidor": ("law", "8078"),
    "cc": ("law", "10406"),
    "codigo civil": ("law", "10406"),
    "cp": ("law", "2848"),
    "codigo penal": ("law", "2848"),
    "codigo penal militar": ("law", "1001"),
    "ctn": ("law", "5172"),
    "codigo tributario nacional": ("law", "5172"),
    "cf": ("cf", None),
    "crfb": ("cf", None),
    "constituicao federal": ("cf", None),
    "constituicao da republica": ("cf", None),
    "codigo eleitoral": ("law", "4737"),
}

CLASS_PATTERNS = [
    ("AGINT", r"\b(?:agint|agravo\s+interno)\b"),
    ("AGRG", r"\b(?:agrg|agravo\s+regimental)\b"),
    ("EDCL", r"\b(?:edcl|embargos?\s+de\s+declaracao)\b"),
    ("ARESP", r"\b(?:aresp|agravo\s+em\s+recurso\s+especial)\b"),
    ("RESP", r"\b(?:resp|r\.?\s*esp\.?|rec\.?\s*esp\.?|recurso\s+especial)\b"),
    ("RCL", r"\b(?:rcl|reclamacao)\b"),
    ("RHC", r"\b(?:rhc|recurso\s+em\s+habeas\s+corpus)\b"),
    ("RMS", r"\b(?:rms|recurso\s+em\s+mandado\s+de\s+seguranca)\b"),
    ("HC", r"\b(?:hc|h\.?\s*c\.?|habeas\s+corpus)\b"),
    ("RE", r"\b(?:re|r\.?\s*e\.?|recurso\s+extraordinario)\b"),
    ("ADI", r"\b(?:adi|adin|acao\s+direta\s+de\s+inconstitucionalidade)\b"),
    ("ADC", r"\b(?:adc|acao\s+declaratoria\s+de\s+constitucionalidade)\b"),
    ("ADPF", r"\b(?:adpf|arguicao\s+de\s+descumprimento\s+de\s+preceito\s+fundamental)\b"),
    ("RSE", r"\b(?:rse|recurso\s+em\s+sentido\s+estrito)\b"),
    ("APL", r"\b(?:apl|apelacao(?:\s+criminal)?)\b"),
    ("RR", r"\b(?:rr|recurso\s+de\s+revista)\b"),
    ("ARR", r"\b(?:arr)\b"),
    ("AIRR", r"\b(?:airr)\b"),
    ("AGRRESPE", r"\b(?:agr-respe|agrrespe)\b"),
    ("RESPE", r"\b(?:respe|recurso\s+especial\s+eleitoral)\b"),
    ("AR", r"\b(?:ar|acao\s+rescisoria)\b"),
    ("AGARR", r"\b(?:agarr)\b"),
]


def ascii_lower(text: str) -> str:
    return unicodedata.normalize("NFD", text).encode("ascii", "ignore").decode().lower()


def normalize_space(text: str) -> str:
    text = ascii_lower(str(text).replace("\\n", " "))
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def class_codes(text: str) -> list[str]:
    text = ascii_lower(str(text))
    return [code for code, pattern in CLASS_PATTERNS if re.search(pattern, text)]


def get_uf(text: str) -> str | None:
    match = UF_RE.search(str(text).replace("\\n", " "))
    return match.group(0).strip(" /-(").upper() if match else None


def raw_numeric_tokens(text: str) -> str | None:
    text = str(text).replace("\\n", " ")
    text = UF_RE.sub(" ", text)
    tokens = re.findall(r"[0-9OolISGg]+", text)
    tokens = [token for token in tokens if any(ch.isdigit() for ch in token)]
    return "".join(tokens) if tokens else None


def expand_ocr(raw: str) -> set[str]:
    values = {""}
    mapping = {
        "O": "0", "o": "0",
        "l": "1", "I": "1",
        "S": "5", "s": "5",
        "G": "6", "g": "69",
    }

    for char in raw:
        options = mapping.get(char, char)
        if not isinstance(options, str):
            options = list(options)
        elif len(options) > 1:
            options = list(options)
        else:
            options = [options]

        values = {prefix + option for prefix in values for option in options}

    return values


def article_number(text: str) -> str | None:
    text = ascii_lower(str(text).replace("\\n", " "))
    match = re.search(
        r"\barts?\.?\s*(\d+(?:\.\d+)*)|\bartigos?\s*(\d+(?:\.\d+)*)",
        text,
    )
    if not match:
        return None
    return re.sub(r"\D", "", match.group(1) or match.group(2))


def law_source(text: str) -> tuple[str, str | None] | None:
    text = ascii_lower(str(text).replace("\\n", " ")).replace("fedcral", "federal")

    match = re.search(
        r"lei\s+complementar\s*(?:n(?:umero)?[.\s]*)?(\d+(?:\.\d+)*)",
        text,
    )
    if match:
        return ("law", re.sub(r"\D", "", match.group(1)))

    match = re.search(
        r"\blei\s*(?:n(?:umero)?[.\s]*)?(\d+(?:\.\d+)*)",
        text,
    )
    if match:
        return ("law", re.sub(r"\D", "", match.group(1)))

    for name in sorted(LAW_SOURCE_MAP, key=len, reverse=True):
        if name in text:
            return LAW_SOURCE_MAP[name]

    return None


def summary_parse(text: str):
    text = ascii_lower(str(text).replace("\\n", " "))
    match = re.search(
        r"\b(?:sumula|5umula|sum\.)\s*(?:vinculante\s*)?"
        r"(?:n(?:[.º°o]|umero)?\s*)?(\d+)",
        text,
    )
    if not match:
        return None

    number = int(match.group(1))
    start = match.start()
    end = match.end()
    is_binding = "vinculante" in text[start:end + 20]

    tribunal = None
    tribunal_match = re.search(
        r"\b(?:do|da|/|-)\s*(stf|stj|tst|tse|stm)\b",
        text,
    )
    if tribunal_match:
        tribunal = tribunal_match.group(1).upper()
    elif is_binding:
        tribunal = "STF"

    return number, tribunal, is_binding


class Resolver:
    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        self.con = sqlite3.connect(self.db_path)
        self.rows = self.con.execute(
            """
            SELECT documento_id, id, tribunal, ano, relator, natureza, tipo, texto
            FROM documentos
            """
        ).fetchall()

        self.by_id = {int(row[1]): row for row in self.rows}
        self.numeric_index: dict[str, set[int]] = defaultdict(set)

        for row in self.rows:
            record_id = int(row[1])
            header = row[7][:6000]
            for match in re.finditer(
                r"(?<!\d)(?:\d[\d.\-/\s]{2,}\d|\d{4,})(?!\d)",
                header,
            ):
                value = re.sub(r"\D", "", match.group())
                if len(value) >= 4:
                    self.numeric_index[value].add(record_id)

        self.law_keys = {}
        self.summary_rows = []

        for row in self.rows:
            record_id = int(row[1])
            if row[5] == "dispositivo":
                first_line = row[7].splitlines()[0]
                self.law_keys[record_id] = (
                    article_number(first_line),
                    law_source(first_line),
                )
            elif row[5] == "sumula":
                self.summary_rows.append(row)

    def resolve(self, trecho: str, tipo: str | None = None) -> tuple[str, int | None]:
        if tipo is None:
            tipo = self.infer_type(trecho)

        if tipo == "lei":
            return self.resolve_law(trecho)

        return self.resolve_jurisprudence(trecho)

    def infer_type(self, trecho: str) -> str:
        text = ascii_lower(str(trecho))
        if re.search(r"\b(?:art\.?|artigo|arts\.?|artigos)\b", text):
            return "lei"
        if "constitui" in text and re.search(r"\b(?:art\.?|artigo)\b", text):
            return "lei"
        return "jurisprudencia"

    def resolve_law(self, trecho: str) -> tuple[str, int | None]:
        article = article_number(trecho)
        source = law_source(trecho)

        if not article or not source:
            return "incompleta", None

        matches = [
            record_id
            for record_id, (record_article, record_source) in self.law_keys.items()
            if record_article == article and record_source == source
        ]

        if len(matches) == 1:
            return "real", matches[0]
        if not matches:
            return "inventada", None
        return "incompleta", None

    def resolve_summary(self, trecho: str):
        parsed = summary_parse(trecho)
        if not parsed:
            return None

        number, tribunal, binding = parsed
        matches = []

        for row in self.summary_rows:
            record_id = int(row[1])
            header = ascii_lower(row[7][:150])
            if not re.search(r"\b" + str(number) + r"\b", header):
                continue

            if tribunal and (row[2] or "").upper() != tribunal:
                continue

            record_binding = "vinculante" in header
            if record_binding == binding:
                matches.append(record_id)

        if len(matches) == 1:
            return "real", matches[0]
        if not matches:
            return "inventada", None
        return "incompleta", None

    def resolve_jurisprudence(self, trecho: str) -> tuple[str, int | None]:
        summary = self.resolve_summary(trecho)
        if summary:
            return summary

        raw = raw_numeric_tokens(trecho)
        if not raw:
            return "incompleta", None

        normalized = ascii_lower(str(trecho))

        # Um ano isolado (ex.: "de 2025") não identifica um processo.
        if (
            len(raw) == 4
            and raw[:2] in {"19", "20"}
            and not re.search(
                r"(?:n[.ºo]?|numero)\s*" + re.escape(raw),
                normalized,
            )
        ):
            return "incompleta", None

        candidates: set[int] = set()
        for variant in expand_ocr(raw):
            candidates.update(self.numeric_index.get(variant, set()))

        if not candidates:
            return "inventada", None

        scored = sorted(
            ((self.score_candidate(trecho, record_id), record_id)
             for record_id in candidates),
            reverse=True,
        )

        best_score = scored[0][0]
        best = [record_id for score, record_id in scored if score == best_score]

        if len(best) == 1 and (
            best_score >= 13
            or (
                len(candidates) == 1
                and len(raw) >= 6
                and bool(class_codes(trecho))
            )
        ):
            return "real", best[0]

        return "incompleta", None

    def score_candidate(self, trecho: str, record_id: int) -> int:
        row = self.by_id[record_id]
        header = row[7][:6000]
        normalized_header = normalize_space(header)
        raw = raw_numeric_tokens(trecho)
        variants = expand_ocr(raw) if raw else set()

        score = 20 if any(
            variant in re.sub(r"\D", "", header[:1500])
            for variant in variants
        ) else 5

        # Desempate importante: "AgInt no Recurso Especial" vs
        # "AgInt nos Embargos de Divergência em REsp".
        citation_norm = normalize_space(trecho)
        if "agint" in citation_norm and (
            "recurso especial" in citation_norm or "resp" in citation_norm
        ):
            if "agint no recurso especial" in normalized_header:
                score += 20

        if "agint" in citation_norm and (
            "agravo em recurso especial" in citation_norm or "aresp" in citation_norm
        ):
            if "agint no agravo em recurso especial" in normalized_header:
                score += 20

        if "agarr" in citation_norm and (
            "agarr" in normalized_header
            or "agravo de instrumento em recurso de revista" in normalized_header
        ):
            score += 20

        aliases = {
            "AGINT": ["agint", "agravo interno"],
            "AGRG": ["agrg", "agravo regimental"],
            "EDCL": ["edcl", "embargos de declaracao"],
            "ARESP": ["aresp", "agravo em recurso especial"],
            "RESP": ["resp", "recurso especial"],
            "RCL": ["rcl", "reclamacao"],
            "RHC": ["rhc", "recurso em habeas corpus"],
            "RMS": ["rms", "recurso em mandado de seguranca"],
            "HC": ["hc", "habeas corpus"],
            "RE": ["recurso extraordinario"],
            "ADI": ["adi", "acao direta de inconstitucionalidade"],
            "ADC": ["adc", "acao declaratoria de constitucionalidade"],
            "ADPF": ["adpf", "arguicao de descumprimento de preceito fundamental"],
            "RSE": ["rse", "recurso em sentido estrito"],
            "APL": ["apl", "apelacao"],
            "RR": ["rr", "recurso de revista"],
            "ARR": ["arr"],
            "AIRR": ["airr"],
            "AGRRESPE": ["agr respe", "agrrespe"],
            "RESPE": ["respe", "recurso especial eleitoral"],
            "AR": ["acao rescisoria"],
            "AGARR": ["agarr", "agravo de instrumento em recurso de revista"],
        }

        for code in class_codes(trecho):
            if any(alias in normalized_header for alias in aliases.get(code, [])):
                score += 8

        citation_norm = normalize_space(trecho)
        for tribunal in ("stf", "stj", "tst", "tse", "stm"):
            if re.search(r"\b" + tribunal + r"\b", citation_norm) and re.search(
                r"\b" + tribunal + r"\b", normalized_header
            ):
                score += 2

        uf = get_uf(trecho)
        if uf and re.search(r"\b" + uf.lower() + r"\b", normalized_header):
            score += 1

        return score


def classify_csv(input_path: str | Path, output_path: str | Path, db_path: str | Path):
    """
    Lê o CSV produzido pelo detector e gera um JSON por documento.
    --saida deve apontar para uma pasta, por exemplo: resultados/json
    """
    resolver = Resolver(db_path)

    with open(input_path, encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        rows = list(reader)

    output_dir = Path(output_path)
    output_dir.mkdir(parents=True, exist_ok=True)

    grouped: dict[str, list[dict]] = defaultdict(list)

    for row in rows:
        documento_id = (row.get("documento_id") or "").strip()
        if not documento_id:
            continue

        trecho = row.get("trecho", "")
        tipo = row.get("tipo") or resolver.infer_type(trecho)
        classificacao, canonical_id = resolver.resolve(trecho, tipo)

        citacao = {
            "inicio": int(row["inicio"]),
            "fim": int(row["fim"]),
            "trecho": trecho,
            "tipo": tipo,
            "classificacao": classificacao,
            "resolucao": (
                {"id_canonico": int(canonical_id)}
                if canonical_id is not None else None
            ),
        }
        grouped[documento_id].append(citacao)

    for documento_id in sorted(grouped):
        payload = {
            "schema": "1.2",
            "documento_id": documento_id,
            "citacoes": grouped[documento_id],
        }
        destination = output_dir / f"{documento_id}.json"
        destination.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    print(f"JSONs gerados: {len(grouped)}")
    print(f"Pasta de saída: {output_dir}")



def main():
    parser = argparse.ArgumentParser(
        description="Classifica citacoes juridicas como real, inventada ou incompleta."
    )
    parser.add_argument("--db", required=True, help="Caminho para desafio1_bracis.db")
    parser.add_argument("--entrada", required=True, help="CSV produzido pelo detector")
    parser.add_argument("--saida", required=True, help="Pasta onde serão gerados os JSONs")
    args = parser.parse_args()

    classify_csv(args.entrada, args.saida, args.db)
    print(f"CSV classificado salvo em: {args.saida}")


if __name__ == "__main__":
    main()
