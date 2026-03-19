"""diagnose_symptom tool — symptom-based troubleshooting with common causes and parts."""
from tools.registry import ToolRegistry

# Built-in symptom knowledge base for common refrigerator/dishwasher issues.
# This provides reliable fallback data; live scraping of PartSelect repair pages
# can supplement this for less common symptoms.
# SYMPTOM_DB = {
#     "refrigerator": {
#         "ice maker not working": {
#             "causes": [
#                 {"cause": "Faulty water inlet valve", "part_type": "Water Inlet Valve", "likelihood": "high"},
#                 {"cause": "Defective ice maker assembly", "part_type": "Ice Maker Assembly", "likelihood": "high"},
#                 {"cause": "Clogged water filter", "part_type": "Water Filter", "likelihood": "medium"},
#                 {"cause": "Frozen water line", "part_type": None, "likelihood": "medium"},
#             ],
#             "source_url": "https://www.partselect.com/Repair/Refrigerator/Not-Making-Ice/",
#         },
#         "leaking water": {
#             "causes": [
#                 {"cause": "Cracked water inlet valve", "part_type": "Water Inlet Valve", "likelihood": "high"},
#                 {"cause": "Damaged door gasket", "part_type": "Door Gasket", "likelihood": "medium"},
#                 {"cause": "Clogged defrost drain", "part_type": "Defrost Drain Kit", "likelihood": "medium"},
#                 {"cause": "Faulty water filter housing", "part_type": "Water Filter Housing", "likelihood": "low"},
#             ],
#             "source_url": "https://www.partselect.com/Repair/Refrigerator/Leaking/",
#         },
#         "not cooling": {
#             "causes": [
#                 {"cause": "Faulty evaporator fan motor", "part_type": "Evaporator Fan Motor", "likelihood": "high"},
#                 {"cause": "Defective compressor start relay", "part_type": "Start Relay", "likelihood": "high"},
#                 {"cause": "Dirty condenser coils", "part_type": None, "likelihood": "medium"},
#                 {"cause": "Bad thermostat", "part_type": "Thermostat", "likelihood": "medium"},
#             ],
#             "source_url": "https://www.partselect.com/Repair/Refrigerator/Refrigerator-Too-Warm/",
#         },
#         "noisy": {
#             "causes": [
#                 {"cause": "Worn evaporator fan motor", "part_type": "Evaporator Fan Motor", "likelihood": "high"},
#                 {"cause": "Faulty condenser fan motor", "part_type": "Condenser Fan Motor", "likelihood": "high"},
#                 {"cause": "Defective compressor", "part_type": "Compressor", "likelihood": "low"},
#             ],
#             "source_url": "https://www.partselect.com/Repair/Refrigerator/Noisy/",
#         },
#     },
#     "dishwasher": {
#         "not draining": {
#             "causes": [
#                 {"cause": "Clogged drain pump", "part_type": "Drain Pump", "likelihood": "high"},
#                 {"cause": "Faulty drain valve", "part_type": "Drain Valve", "likelihood": "medium"},
#                 {"cause": "Blocked garbage disposal connection", "part_type": None, "likelihood": "medium"},
#             ],
#             "source_url": "https://www.partselect.com/Repair/Dishwasher/Not-Draining/",
#         },
#         "not cleaning": {
#             "causes": [
#                 {"cause": "Clogged spray arm", "part_type": "Spray Arm", "likelihood": "high"},
#                 {"cause": "Faulty wash pump", "part_type": "Wash Pump", "likelihood": "medium"},
#                 {"cause": "Worn water inlet valve", "part_type": "Water Inlet Valve", "likelihood": "medium"},
#             ],
#             "source_url": "https://www.partselect.com/Repair/Dishwasher/Not-Cleaning-Properly/",
#         },
#         "leaking": {
#             "causes": [
#                 {"cause": "Damaged door gasket", "part_type": "Door Gasket", "likelihood": "high"},
#                 {"cause": "Cracked door latch", "part_type": "Door Latch", "likelihood": "medium"},
#                 {"cause": "Faulty water inlet valve", "part_type": "Water Inlet Valve", "likelihood": "medium"},
#             ],
#             "source_url": "https://www.partselect.com/Repair/Dishwasher/Leaking/",
#         },
#         "not starting": {
#             "causes": [
#                 {"cause": "Defective door latch/switch", "part_type": "Door Latch", "likelihood": "high"},
#                 {"cause": "Faulty control board", "part_type": "Control Board", "likelihood": "medium"},
#                 {"cause": "Blown thermal fuse", "part_type": "Thermal Fuse", "likelihood": "medium"},
#             ],
#             "source_url": "https://www.partselect.com/Repair/Dishwasher/Will-Not-Start/",
#         },
#     },
# }



def register_symptom_tool(
    registry: ToolRegistry,
    knowledge_service,
) -> None:
    @registry.register(
        name="diagnose_symptom",
        description="Diagnose an appliance problem by symptom. Returns possible causes and recommended replacement parts.",
        parameters={
            "type": "object",
            "properties": {
                "appliance_type": {
                    "type": "string",
                    "enum": ["refrigerator", "dishwasher"],
                    "description": "Type of appliance",
                },
                "symptom": {
                    "type": "string",
                    "description": "Description of the problem (e.g., 'ice maker not working', 'leaking water', 'not draining')",
                },
                "model_number": {
                    "type": "string",
                    "description": "Optional model number for more specific results",
                },
            },
            "required": ["appliance_type", "symptom"],
        },
    )
    async def diagnose_symptom(
        appliance_type: str, symptom: str, model_number: str = ""
    ) -> dict:
        # Structured-first troubleshooting evidence from the indexed dataset.
        try:
            structured = await knowledge_service.diagnose_troubleshooting(
                appliance_type=appliance_type,
                symptom=symptom,
                model_number=model_number,
            )
            likely_causes = structured.get("causes") or []
            source_urls = structured.get("source_urls") or []
            if likely_causes:
                return {
                    "causes": likely_causes,
                    "symptom": symptom,
                    "matched_symptom": structured.get("matched_symptom"),
                    "appliance_type": appliance_type,
                    "model_number": model_number,
                    "source_url": source_urls[0] if source_urls else "",
                }
        except Exception:
            pass

        return {
            "causes": [],
            "symptom": symptom,
            "appliance_type": appliance_type,
            "model_number": model_number,
            "message": f"I don't have specific troubleshooting data for '{symptom}' on {appliance_type}s. "
                       f"Please visit partselect.com for more repair help.",
            "source_url": f"https://www.partselect.com/Repair/{appliance_type.title()}/",
        }
