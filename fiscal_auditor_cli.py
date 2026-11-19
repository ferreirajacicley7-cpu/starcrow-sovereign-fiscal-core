This repository hosts the open reference CLI and schema validator. For full Dedicated Private Node deployment, ERP integration, and custom tax rule packs:

Company: Starcrow Tech (Intelligent Automation & Sovereign Infrastructure)

Founder & CVO: Jacicley Ferreira (LinkedIn)

Direct Contact: starcrowtech@gmail.com | Telegram: @starcrow_tech

### 3. Código Público Limpo para Subir (`fiscal_auditor_cli.py` + `sample_nfe_sefaz.xml`)

Para não vazar nenhum segredo industrial do seu kernel completo, suba esta **versão CLI aberta e funcional** (qualquer contador, dev ou CTO que clonar o repo consegue rodar na hora e ver o motor funcionando):

#### Arquivo 1: `fiscal_auditor_cli.py`
```python
import sys
import json
import hashlib
import argparse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

NFE_NS = {"nfe": "http://www.portalfiscal.inf.br/nfe"}

def compute_sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()

def audit_nfe_xml(xml_path: str, ibs_cbs_ref_rate: float = 0.265) -> dict:
    with open(xml_path, "rb") as f:
        raw_bytes = f.read()

    doc_hash = compute_sha256(raw_bytes)
    root = ET.fromstring(raw_bytes)

    inf_nfe = root.find(".//nfe:infNFe", NFE_NS)
    if inf_nfe is None:
        raise ValueError("Invalid NF-e XML structure: missing <infNFe>.")

    nfe_id = inf_nfe.attrib.get("Id", "UNKNOWN")
    emit_nome = root.findtext(".//nfe:emit/nfe:xNome", default="N/A", namespaces=NFE_NS)
    emit_cnpj = root.findtext(".//nfe:emit/nfe:CNPJ", default="N/A", namespaces=NFE_NS)

    findings = []
    total_prod_value = 0.0
    total_legacy_tax = 0.0

    for det in root.findall(".//nfe:det", NFE_NS):
        item_num = det.attrib.get("nItem", "?")
        prod = det.find("nfe:prod", NFE_NS)
        imposto = det.find("nfe:imposto", NFE_NS)

        x_prod = prod.findtext("nfe:xProd", default="", namespaces=NFE_NS)
        ncm = prod.findtext("nfe:NCM", default="", namespaces=NFE_NS)
        cfop = prod.findtext("nfe:CFOP", default="", namespaces=NFE_NS)
        v_prod = float(prod.findtext("nfe:vProd", default="0", namespaces=NFE_NS))
        total_prod_value += v_prod

        # Check 1: Generic / Invalid NCM
        if ncm == "00000000" or len(ncm) != 8:
            findings.append({
                "severity": "HIGH",
                "item": item_num,
                "product": x_prod,
                "code": "INVALID_NCM",
                "detail": f"NCM '{ncm}' is generic or malformed. High risk of SEFAZ rejection or tax credit disallowance."
            })

        # Extract legacy taxes (ICMS, PIS, COFINS)
        v_icms = float(imposto.findtext(".//nfe:vICMS", default="0", namespaces=NFE_NS) or 0)
        cst_icms = imposto.findtext(".//nfe:ICMS//nfe:CST", default="", namespaces=NFE_NS)
        v_pis = float(imposto.findtext(".//nfe:PIS//nfe:vPIS", default="0", namespaces=NFE_NS) or 0)
        v_cofins = float(imposto.findtext(".//nfe:COFINS//nfe:vCOFINS", default="0", namespaces=NFE_NS) or 0)

        item_legacy_tax = v_icms + v_pis + v_cofins
        total_legacy_tax += item_legacy_tax

        # Check 2: Suspicious Tax Exemption (CST 40) on commercial CFOP
        if cst_icms == "40" and v_icms == 0.0 and cfop.startswith(("51", "61")):
            findings.append({
                "severity": "CRITICAL",
                "item": item_num,
                "product": x_prod,
                "code": "UNJUSTIFIED_ICMS_EXEMPTION",
                "detail": f"CST 40 applied on commercial sale CFOP {cfop} (Value: R$ {v_prod:,.2f}). Potential omitted ICMS liability."
            })

    projected_ibs_cbs = round(total_prod_value * ibs_cbs_ref_rate, 2)
    net_transition_delta = round(projected_ibs_cbs - total_legacy_tax, 2)

    report = {
        "engine": "Starcrow Sovereign Core CLI v1.0",
        "audited_at_utc": datetime.now(timezone.utc).isoformat(),
        "nfe_key": nfe_id,
        "issuer": {"name": emit_nome, "cnpj": emit_cnpj},
        "sha256_evidence_hash": doc_hash,
        "financial_summary_brl": {
            "total_goods_value": round(total_prod_value, 2),
            "legacy_taxes_paid": round(total_legacy_tax, 2),
            "projected_ibs_cbs_26_5pct": projected_ibs_cbs,
            "net_transition_delta": net_transition_delta
        },
        "compliance_findings_count": len(findings),
        "findings": findings
    }
    return report

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Starcrow Sovereign Fiscal & IBS/CBS Auditor CLI")
    parser.add_argument("--xml", required=True, help="Path to NF-e XML file")
    args = parser.parse_args()

    result = audit_nfe_xml(args.xml)
    print(json.dumps(result, indent=2, ensure_ascii=False))
