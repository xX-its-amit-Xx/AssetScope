import httpx
import respx

from assetscope.models import ToolResult
from assetscope.tools import build_default_registry
from assetscope.tools.base import Tool, ToolRegistry
from assetscope.tools.chembl import ChemblTool
from assetscope.tools.clinical_trials import ClinicalTrialsTool
from assetscope.tools.literature import LiteratureTool
from assetscope.tools.open_targets import OpenTargetsTool


@respx.mock
def test_clinical_trials_parsing():
    respx.route(method="GET", host="clinicaltrials.gov", path="/api/v2/studies").mock(
        return_value=httpx.Response(
            200,
            json={
                "studies": [
                    {
                        "protocolSection": {
                            "identificationModule": {"nctId": "NCT04184622", "briefTitle": "SURMOUNT-1 tirzepatide"},
                            "statusModule": {"overallStatus": "COMPLETED"},
                            "designModule": {"phases": ["PHASE3"]},
                            "sponsorCollaboratorsModule": {"leadSponsor": {"name": "Eli Lilly"}},
                            "conditionsModule": {"conditions": ["Obesity"]},
                            "armsInterventionsModule": {"interventions": [{"type": "DRUG", "name": "Tirzepatide"}]},
                            "descriptionModule": {"briefSummary": "A study of tirzepatide in obesity."},
                        }
                    }
                ],
                "totalCount": 1,
            },
        )
    )
    res = ClinicalTrialsTool().run(query="tirzepatide obesity", phase="3")
    assert len(res.items) == 1
    cit = res.items[0].citation
    assert cit.id == "NCT04184622"
    assert "NCT04184622" in cit.url
    assert res.items[0].fields["lead_sponsor"] == "Eli Lilly"
    assert "PHASE3" in res.items[0].fields["phase"]


@respx.mock
def test_clinical_trials_phase_filter_excludes():
    respx.route(method="GET", host="clinicaltrials.gov", path="/api/v2/studies").mock(
        return_value=httpx.Response(
            200,
            json={"studies": [{"protocolSection": {
                "identificationModule": {"nctId": "NCT1", "briefTitle": "t"},
                "designModule": {"phases": ["PHASE1"]},
            }}], "totalCount": 1},
        )
    )
    res = ClinicalTrialsTool().run(query="x", phase="3")
    assert res.items == []  # PHASE1 trial filtered out when asking for phase 3


@respx.mock
def test_chembl_molecule_and_mechanism():
    respx.route(method="GET", host="www.ebi.ac.uk", path="/chembl/api/data/molecule/search.json").mock(
        return_value=httpx.Response(200, json={"molecules": [
            {"molecule_chembl_id": "CHEMBL4297839", "pref_name": "TIRZEPATIDE", "max_phase": "4.0"}
        ]})
    )
    respx.route(method="GET", host="www.ebi.ac.uk", path="/chembl/api/data/mechanism.json").mock(
        return_value=httpx.Response(200, json={"mechanisms": [
            {"mechanism_of_action": "Glucose-dependent insulinotropic polypeptide receptor agonist",
             "action_type": "AGONIST", "target_chembl_id": "CHEMBL2034"}
        ]})
    )
    res = ChemblTool().run(compound_or_target="tirzepatide")
    assert res.items[0].citation.id == "CHEMBL4297839"
    assert res.items[0].fields["max_phase"] == 4
    assert "agonist" in res.items[0].content.lower()


@respx.mock
def test_literature_esearch_efetch():
    respx.route(method="GET", host="eutils.ncbi.nlm.nih.gov", path="/entrez/eutils/esearch.fcgi").mock(
        return_value=httpx.Response(200, json={"esearchresult": {"idlist": ["35658024"]}})
    )
    xml = (
        "<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>35658024</PMID>"
        "<Article><Journal><Title>NEJM</Title></Journal>"
        "<ArticleTitle>Tirzepatide Once Weekly for the Treatment of Obesity</ArticleTitle>"
        "<Abstract><AbstractText Label='RESULTS'>20.9% weight loss.</AbstractText></Abstract>"
        "</Article></MedlineCitation></PubmedArticle></PubmedArticleSet>"
    )
    respx.route(method="GET", host="eutils.ncbi.nlm.nih.gov", path="/entrez/eutils/efetch.fcgi").mock(
        return_value=httpx.Response(200, text=xml)
    )
    res = LiteratureTool().run(query="tirzepatide obesity")
    assert res.items[0].citation.id == "35658024"
    assert "Tirzepatide" in res.items[0].citation.title
    assert "weight loss" in res.items[0].content.lower()


@respx.mock
def test_open_targets_target_resolution():
    def handler(request):
        body = request.content.decode()
        if "Resolve" in body:
            return httpx.Response(200, json={"data": {"search": {"hits": [
                {"id": "ENSG00000010671", "entity": "target", "name": "BTK"}
            ]}}})
        return httpx.Response(200, json={"data": {"target": {
            "id": "ENSG00000010671", "approvedSymbol": "BTK", "approvedName": "Bruton tyrosine kinase",
            "tractability": [{"label": "Approved Drug", "modality": "SM", "value": True}],
            "associatedDiseases": {"rows": [{"score": 0.72, "disease": {"id": "EFO_0000095", "name": "chronic lymphocytic leukemia"}}]},
        }}})

    respx.route(method="POST", host="api.platform.opentargets.org").mock(side_effect=handler)
    res = OpenTargetsTool().run(target_or_disease="BTK")
    assert res.items[0].citation.id == "OT:ENSG00000010671"
    assert "BTK" in res.items[0].content
    assert "chronic lymphocytic leukemia" in res.items[0].content


def test_registry_dispatch_errors():
    class Boom(Tool):
        name = "boom"
        description = "x"
        input_schema = {"type": "object", "properties": {}}

        def run(self, **kwargs) -> ToolResult:
            raise ValueError("kaboom")

    reg = ToolRegistry([Boom()])
    assert reg.dispatch("nope", {}).error.startswith("Unknown tool")
    assert "kaboom" in reg.dispatch("boom", {}).error


def test_default_registry_has_five_tools():
    reg = build_default_registry()
    assert set(reg.names()) == {
        "search_clinical_trials", "search_open_targets", "search_chembl",
        "search_literature", "retrieve",
    }
    # every schema is Anthropic-tool shaped
    for s in reg.anthropic_schemas():
        assert {"name", "description", "input_schema"} <= set(s)
