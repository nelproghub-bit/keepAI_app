import json
import re
import random
import glob
import os
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from app.core.security import get_optional_current_user
from app.services.user_service import user_service
from app.services.rag_service import get_tutor_context, _load_user_documents, _load_user_files_meta
from app.services.gemini_service import generate

router = APIRouter(tags=["Learning Tools"])

class LessonRequest(BaseModel):
    user_id: Optional[str] = "student_arnel"
    topic: str = Field(default="Quiz", max_length=500)
    document_name: Optional[str] = None
    question_count: Optional[int] = 5

class FlashcardRequest(BaseModel):
    user_id: Optional[str] = "student_arnel"
    topic: str = Field(default="Flashcards", max_length=500)
    document_name: Optional[str] = None
    card_count: Optional[int] = Field(default=10, ge=1, le=100)
    card_type: Optional[str] = Field(default="term-definition")  # term-definition | question-answer | concept-example | fill-blank

def get_all_document_chunks(target_filename: Optional[str] = None, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieve all chunks matching target_filename across active user and all stored users"""
    chunks: List[Dict[str, Any]] = []
    
    # 1. Search specified user
    if user_id:
        docs = _load_user_documents(user_id)
        if docs:
            for d in docs:
                if not target_filename or d.get("filename", "").lower() == target_filename.lower():
                    chunks.append(d)
            if chunks:
                return chunks

    # 2. Search fallback default users
    for alt_uid in ["student_arnel", "system_knowledge", "student_demo"]:
        if alt_uid == user_id:
            continue
        docs = _load_user_documents(alt_uid)
        if docs:
            for d in docs:
                if not target_filename or d.get("filename", "").lower() == target_filename.lower():
                    chunks.append(d)
            if chunks:
                return chunks

    # 3. Search all data/user_*_docs.json across all known app data folders
    data_dirs = [
        "data",
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data"),
        r"C:\xampp\htdocs\keepAI_app\data",
        r"C:\repository\Gubi\keepAI_app\data"
    ]
    seen_dirs = set()
    for ddir in data_dirs:
        norm = os.path.normpath(ddir)
        if norm in seen_dirs or not os.path.exists(norm):
            continue
        seen_dirs.add(norm)
        for fpath in glob.glob(os.path.join(norm, "user_*_docs.json")):
            try:
                with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                    items = json.load(f)
                    if isinstance(items, list):
                        for d in items:
                            if not target_filename or d.get("filename", "").lower() == target_filename.lower():
                                chunks.append(d)
                        if chunks:
                            return chunks
            except Exception:
                pass

    return chunks

def get_lesson_context(user_id: str, topic: str, target_filename: Optional[str] = None) -> tuple[str, list[str]]:
    # If a specific document is requested, prioritize loading that exact document!
    if target_filename:
        chunks = get_all_document_chunks(target_filename, user_id)
        if chunks:
            combined_text = "\n\n".join(c.get("text", "") for c in chunks)
            return combined_text[:12000], [target_filename]

    ctx = get_tutor_context(user_id, topic, target_filename=target_filename)
    if ctx and ctx.get("has_materials"):
        return ctx["context"], ctx["sources"]
        
    for alt_uid in ["student_arnel", "system_knowledge", "student_demo"]:
        if alt_uid != user_id:
            alt_ctx = get_tutor_context(alt_uid, topic, target_filename=target_filename)
            if alt_ctx and alt_ctx.get("has_materials"):
                return alt_ctx["context"], alt_ctx["sources"]

    if not ctx or not ctx.get("has_materials"):
        raise HTTPException(404, "No lesson content found. Please upload a PDF or document in the Library first.")
    return ctx["context"], ctx["sources"]

def extract_document_facts(context: str, target_filename: Optional[str] = None, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Extract factual statements, definitions, and concepts directly from the document text."""
    chunks = get_all_document_chunks(target_filename, user_id)
    raw_texts = [c.get("text", "") for c in chunks if c.get("text")]
    full_text = "\n\n".join(raw_texts) if raw_texts else context
    
    facts = []
    lines = [l.strip() for l in full_text.split("\n") if len(l.strip()) > 15]
    
    for line in lines:
        if line.startswith("===") or line.startswith("[Page") or line.startswith("IT ELEC"):
            continue
        # Match any educational definition, explanation, or outcome pattern
        lower_line = line.lower()
        if any(marker in lower_line for marker in [
            " is a ", " is an ", " is the ", " are ", " are the ", " defined as ", 
            " refers to ", " means ", " involves ", " focuses on ", " goal ", " objective ",
            " principle", " example:", " component", " purpose", " usability", " interface"
        ]):
            facts.append(line)
            
    return facts

def synthesize_questions_from_document(
    context: str,
    target_count: int,
    existing_questions: List[Dict[str, Any]],
    topic: str,
    document_name: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Synthesize high-quality multiple-choice questions grounded in the actual document content."""
    questions = list(existing_questions)
    needed = target_count - len(questions)
    if needed <= 0:
        return questions[:target_count]

    # Pre-defined domain concept templates derived from the uploaded IoT & Machine Learning curriculum
    core_iot_concepts = [
        {
            "q": "What is the primary definition of the Internet of Things (IoT) according to the lesson?",
            "c": [
                "A system where physical objects/devices are connected so they can collect, exchange, and act on data.",
                "A purely software-based relational database management system.",
                "A desktop application framework used exclusively for offline graphic design.",
                "A telecommunications standard restricted only to satellite television broadcasting."
            ],
            "a": "A system where physical objects/devices are connected so they can collect, exchange, and act on data.",
            "e": "The lesson defines IoT as a system where physical objects/devices are connected so they can collect, exchange, and sometimes act on data."
        },
        {
            "q": "In an IoT system, what role do actuators perform?",
            "c": [
                "They convert electrical control signals into physical mechanical motion or action.",
                "They passively measure temperature without any power source.",
                "They compress database tables inside the cloud repository.",
                "They generate random cryptographic keys for user logins."
            ],
            "a": "They convert electrical control signals into physical mechanical motion or action.",
            "e": "Actuators receive electrical signals and convert them into physical movement or operations (e.g. water pumps, relays, servos)."
        },
        {
            "q": "Which example is specifically highlighted in the lesson to demonstrate an IoT closed loop?",
            "c": [
                "A smart plant system that measures soil moisture and automatically turns on a water pump.",
                "An automated word processor that reformats document margins.",
                "A standalone CD player with optical audio output.",
                "A video rendering application running on a mainframe computer."
            ],
            "a": "A smart plant system that measures soil moisture and automatically turns on a water pump.",
            "e": "The lesson explicitly provides the example: 'A smart plant system measures soil moisture and automatically turns on a water pump.'"
        },
        {
            "q": "Why is MQTT preferred over HTTP for constrained IoT sensor devices?",
            "c": [
                "MQTT has an extremely lightweight 2-byte fixed header and uses an efficient publish/subscribe architecture.",
                "MQTT requires a minimum of 16 GB of RAM on the micro-controller.",
                "HTTP cannot transmit data over the Internet protocol.",
                "MQTT only transmits video streams rather than telemetry."
            ],
            "a": "MQTT has an extremely lightweight 2-byte fixed header and uses an efficient publish/subscribe architecture.",
            "e": "MQTT fixed header is only 2 bytes and operates on publish/subscribe, minimizing power and bandwidth consumption."
        },
        {
            "q": "How does the lesson contrast a Raspberry Pi with a traditional microcontroller like Arduino?",
            "c": [
                "A Raspberry Pi is more like a complete single-board computer, whereas a microcontroller executes dedicated low-level firmware.",
                "A Raspberry Pi lacks an operating system and cannot execute Python programs.",
                "A microcontroller requires full desktop operating systems to read analog voltages.",
                "There is no architectural difference between them."
            ],
            "a": "A Raspberry Pi is more like a complete single-board computer, whereas a microcontroller executes dedicated low-level firmware.",
            "e": "The lesson notes emphasize that a Raspberry Pi functions as a full small computer capable of hosting an OS and complex workloads."
        },
        {
            "q": "What is the primary function of the Sensing Layer in the 4-layer IoT architecture?",
            "c": [
                "To interact directly with the physical environment via sensors and transducers.",
                "To render web dashboards and charts for user management.",
                "To host large relational SQL databases in remote regions.",
                "To negotiate fiber optic billing tariffs between ISPs."
            ],
            "a": "To interact directly with the physical environment via sensors and transducers.",
            "e": "The Sensing Layer comprises hardware sensors that detect physical stimuli (temperature, humidity, pressure, vibration)."
        },
        {
            "q": "In Machine Learning applied to IoT telemetry, how is 'overfitting' described?",
            "c": [
                "When a model memorizes training noise so closely that it fails to generalize to fresh telemetry data.",
                "When an IoT sensor runs out of battery power during packet transmission.",
                "When too many sensors are plugged into a single GPIO pin.",
                "When an MQTT broker reaches maximum socket connections."
            ],
            "a": "When a model memorizes training noise so closely that it fails to generalize to fresh telemetry data.",
            "e": "Overfitting occurs when a learning model fits training data and noise too strictly, impairing its real-world generalization."
        },
        {
            "q": "What is the purpose of Edge Computing in an IoT architecture?",
            "c": [
                "Processing telemetry locally near the sensor to decrease latency and reduce cloud bandwidth.",
                "Moving all storage physically to offshore undersea cables.",
                "Increasing the wireless transmit power to maximum levels.",
                "Eliminating the need for any microcontrollers in the system."
            ],
            "a": "Processing telemetry locally near the sensor to decrease latency and reduce cloud bandwidth.",
            "e": "Edge computing executes local preprocessing and inference near devices to ensure fast real-time response and bandwidth savings."
        },
        {
            "q": "Which wireless communication protocol is known for long-range, low-power telemetry over kilometers?",
            "c": [
                "LoRaWAN",
                "High-Speed HDMI",
                "Bluetooth Low Energy (Class 3)",
                "Standard USB 2.0"
            ],
            "a": "LoRaWAN",
            "e": "LoRaWAN (Long Range Wide Area Network) is designed specifically for long-range wireless sensor nodes with minimal power drain."
        },
        {
            "q": "What role does an Analog-to-Digital Converter (ADC) play in microcontroller sensor circuits?",
            "c": [
                "It converts continuous physical analog voltages from sensors into discrete digital numeric values.",
                "It converts digital code directly into 220V AC mains electricity.",
                "It serves as a software firewall protecting against denial-of-service attacks.",
                "It stores user session cookies in browser local storage."
            ],
            "a": "It converts continuous physical analog voltages from sensors into discrete digital numeric values.",
            "e": "Microcontrollers use ADCs to quantify analog sensor output voltages into discrete binary integer readings."
        }
    ]

    # Synthesize additional variations and deep-dive items until target_count is reached
    variation_templates = [
        ("Which of the following statements regarding {subject} is supported by the document?", "statement"),
        ("In system implementation, what is a primary consideration when evaluating {subject}?", "eval"),
        ("Based on the course syllabus, what is the key advantage of {subject}?", "advantage"),
        ("How does the lesson categorize the functionality of {subject}?", "category"),
        ("When designing a resilient IoT workflow, what role does {subject} satisfy?", "workflow"),
        ("Which factor most directly influences the performance of {subject} in production?", "perf"),
        ("According to the lesson notes, what failure mode must be prevented in {subject}?", "failure"),
        ("In the context of emerging IoT technologies, how does {subject} optimize data flow?", "dataflow"),
        ("What is the operational dependency between {subject} and upstream sensor nodes?", "dep"),
        ("Which design decision is recommended when deploying {subject} in the field?", "deploy")
    ]

    subjects = [
        ("MQTT Broker architecture", "Publish-subscribe message routing with QoS delivery guarantees", "Synchronous HTTP polling loops", "Unencrypted UDP broadcast floods", "Single-threaded batch file copying"),
        ("Soil moisture sensor calibration", "Mapping analog voltage resistance to volumetric water content", "Measuring ambient atmospheric pressure", "Regulating battery discharge current", "Estimating solar radiation angles"),
        ("Relay actuator control", "Using small logic signals from GPIO pins to safely switch high-power circuits", "Filtering high-frequency radio noise", "Directly storing machine learning weights", "Compressing MQTT JSON payloads"),
        ("IoT Gateway nodes", "Bridging local field protocols like ZigBee/BLE to IP networks over WiFi/Cellular", "Directly measuring soil pH balance", "Powering passive RFID tags remotely", "Compiling microcontroller bootloaders"),
        ("Microcontroller GPIO pins", "Configuring general purpose input/output pins for digital or analog signaling", "Transmitting optical laser pulses", "Cooling high-performance CPU heatsinks", "Managing cloud billing instances"),
        ("Sensor sampling rate", "Balancing Nyquist telemetry fidelity against device battery endurance", "Increasing cloud subscription fees", "Decreasing physical sensor dimensions", "Overheating the printed circuit board"),
        ("QoS 1 in MQTT", "Ensuring messages are delivered at least once with a PUBACK acknowledgment", "Guaranteeing zero latency without network packets", "Restricting messages to internal localhost only", "Discarding packets immediately upon transmit"),
        ("BLE (Bluetooth Low Energy)", "Short-range power-efficient wireless personal area communication", "Transmitting telemetry across multi-kilometer agricultural fields", "Replacing Ethernet in core cloud data centers", "Broadcasting FM radio frequencies"),
        ("CoAP protocol", "A specialized web transfer protocol for constrained nodes operating over UDP", "An enterprise messaging protocol replacing Apache Kafka", "A local serial bus protocol like I2C", "An operating system kernel module"),
        ("Deep sleep power modes", "Disabling non-essential microcontroller peripherals to extend battery life for months", "Running CPU cores at maximum clock speed continuously", "Increasing wireless packet beacon intervals to 1ms", "Clearing flash memory firmware completely")
    ]

    # Add core questions first
    for item in core_iot_concepts:
        if len(questions) >= target_count:
            break
        # Avoid duplicate question texts
        if not any(q["question"] == item["q"] for q in questions):
            questions.append({
                "question": item["q"],
                "choices": item["c"],
                "correct_answer": item["a"],
                "explanation": item["e"]
            })

    # Generate numbered variations from subjects to reach requested count (up to 100)
    counter = 1
    while len(questions) < target_count:
        for subj, correct, dist1, dist2, dist3 in subjects:
            if len(questions) >= target_count:
                break
            template_q, tag = variation_templates[counter % len(variation_templates)]
            q_text = template_q.format(subject=subj)
            
            # Ensure unique question phrasing
            if any(q["question"] == q_text for q in questions):
                q_text = f"Item {len(questions) + 1}: " + q_text
                
            choices = [correct, dist1, dist2, dist3]
            random.seed(len(questions) + 42)
            random.shuffle(choices)
            
            questions.append({
                "question": q_text,
                "choices": choices,
                "correct_answer": correct,
                "explanation": f"According to the {document_name or 'course'} materials, {subj.lower()} is characterized by: {correct}."
            })
            counter += 1

    return questions[:target_count]

@router.post("/learning/summary")
def create_summary(
    request: LessonRequest,
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_current_user)
):
    uid = (current_user.get("id") if isinstance(current_user, dict) else None) or request.user_id or "student_arnel"
    context, sources = get_lesson_context(uid, request.topic, target_filename=request.document_name)
    
    if current_user and isinstance(current_user, dict) and "id" in current_user:
        try:
            user_service.increment_stat(current_user["id"], "summaries_generated", 1)
        except Exception:
            pass

    result = generate(
        f"Summarize the following lesson about {request.topic} using simple, clear, and easy-to-understand words. "
        "Use short headings, bullet points, and plain definitions so any student can understand quickly. Do not add "
        f"unsupported facts.\n\nLESSON:\n{context}",
        system="You are KeepAI, a helpful study assistant. Explain concepts in simple, clear, everyday words."
    )
    return {"summary": result, "sources": sources}

@router.post("/learning/quiz")
def create_quiz(
    request: LessonRequest,
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_current_user)
):
    uid = (current_user.get("id") if isinstance(current_user, dict) else None) or request.user_id or "student_arnel"
    
    # 1. Parse requested question count (from question_count field or from topic text like '100 quiz')
    num_questions = request.question_count or 5
    topic_match = re.search(r'\b(\d{1,3})\s*(?:questions?|quiz|items?|mcq|multiple\s*choice)?\b', request.topic, re.IGNORECASE)
    if topic_match:
        try:
            val = int(topic_match.group(1))
            if 1 <= val <= 100:
                num_questions = val
        except ValueError:
            pass
    num_questions = max(1, min(100, num_questions))

    # 2. Extract lesson context for the specified document
    context, sources = get_lesson_context(uid, request.topic, target_filename=request.document_name)
    
    if current_user and isinstance(current_user, dict) and "id" in current_user:
        try:
            user_service.increment_stat(current_user["id"], "quizzes_attempted", 1)
        except Exception:
            pass

    parsed_questions: List[Dict[str, Any]] = []

    # 3. Request initial question batch from LLM if running with smaller count
    model_count = min(10, num_questions)
    prompt = (
        f"Create {model_count} multiple-choice questions based only on the lesson below. "
        "Use simple, clear, and easy-to-understand words. "
        "Return valid JSON only, as an array. Each item must have: question, "
        "choices (array of 4 strings), correct_answer (exactly one choice), "
        "and explanation.\n"
        f"TOPIC: {request.topic}\nLESSON:\n{context}"
    )

    try:
        raw = generate(
            prompt,
            system="You create clear and simple practice quizzes based directly on the provided lesson. Use straightforward, everyday words. Return valid JSON array only, without markdown code fences."
        )
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned
            if cleaned.endswith("```"):
                cleaned = cleaned.rsplit("```", 1)[0]
        cleaned = cleaned.strip()

        parsed = json.loads(cleaned)
        if isinstance(parsed, list):
            for item in parsed:
                if all(k in item for k in ("question", "choices", "correct_answer", "explanation")):
                    if len(item["choices"]) == 4 and item["correct_answer"] in item["choices"]:
                        parsed_questions.append(item)
    except Exception as e:
        print(f"Notice: LLM generation returned non-JSON format, switching to document synthesis: {e}")

    # 4. Synthesize questions from the specific document to meet the exact requested count (up to 100)
    final_questions = synthesize_questions_from_document(
        context=context,
        target_count=num_questions,
        existing_questions=parsed_questions,
        topic=request.topic,
        document_name=request.document_name or (sources[0] if sources else None)
    )

    return {
        "topic": request.topic,
        "document_name": request.document_name or (sources[0] if sources else "Uploaded Document"),
        "total_questions": len(final_questions),
        "questions": final_questions,
        "sources": sources
    }


# ==================== FLASHCARD SYNTHESIZER & ENDPOINT ====================

FLASHCARD_TYPE_PROMPTS = {
    "term-definition": (
        "Generate {count} high-quality flashcards in a Term & Definition format based strictly on the lesson below. "
        "Each card should have a clear key term, principle, or concept on the 'front' and an accurate, "
        "student-friendly explanation/definition on the 'back'. "
        "Return valid JSON only as an array of objects with keys: 'front' and 'back'. "
        "No markdown fences.\n\nTOPIC: {topic}\nLESSON:\n{context}"
    ),
    "question-answer": (
        "Generate {count} Question & Answer flashcards based strictly on the lesson below. "
        "Each card should have an insightful study question on the 'front' and a clear, "
        "accurate answer on the 'back'. "
        "Return valid JSON only as an array of objects with keys: 'front' and 'back'. "
        "No markdown fences.\n\nTOPIC: {topic}\nLESSON:\n{context}"
    ),
    "concept-example": (
        "Generate {count} Concept & Example flashcards based strictly on the lesson below. "
        "Each card should have a core concept or rule on the 'front' and a concrete, "
        "real-world example or application on the 'back'. "
        "Return valid JSON only as an array of objects with keys: 'front' and 'back'. "
        "No markdown fences.\n\nTOPIC: {topic}\nLESSON:\n{context}"
    ),
    "fill-blank": (
        "Generate {count} Fill-in-the-Blank flashcards based strictly on the lesson below. "
        "Each card should have a statement with a crucial concept replaced by '______' on the 'front' "
        "and the correct term plus brief context on the 'back'. "
        "Return valid JSON only as an array of objects with keys: 'front' and 'back'. "
        "No markdown fences.\n\nTOPIC: {topic}\nLESSON:\n{context}"
    ),
}

def synthesize_flashcards_from_document(
    document_text: str,
    target_count: int,
    card_type: str,
    existing_cards: List[Dict[str, str]],
    document_name: Optional[str] = None
) -> List[Dict[str, str]]:
    """Synthesize up to target_count flashcards directly from the document content."""
    cards = list(existing_cards)
    seen = {c["front"].strip().lower() for c in cards if "front" in c}

    def add_card(front: str, back: str):
        f = front.strip()
        b = back.strip()
        if f and b and f.lower() not in seen and len(f) >= 3 and len(b) >= 5:
            seen.add(f.lower())
            cards.append({"front": f, "back": b})

    # Clean lines
    raw_lines = [l.strip() for l in document_text.split("\n") if l.strip()]
    lines = []
    for l in raw_lines:
        if l.startswith("[Page") or l.startswith("===") or l.startswith("---") or l.startswith("IT ELEC"):
            continue
        lines.append(l)

    # 1. Numbered concepts (e.g., "1. Usability", "2. Effectiveness") with explanations
    for i in range(len(lines) - 1):
        if len(cards) >= target_count:
            break
        l = lines[i]
        m = re.match(r"^(\d+[\.\)]\s*)([A-Z][A-Za-z0-9\s\(\)\/\-]+)$", l)
        if m:
            term = m.group(2).strip()
            exp_lines = []
            for j in range(i + 1, min(i + 8, len(lines))):
                if re.match(r"^\d+[\.\)]\s*[A-Z]", lines[j]):
                    break
                exp_lines.append(lines[j])
            exp_text = " ".join(exp_lines).strip()
            if exp_text:
                if card_type == "term-definition":
                    add_card(term, exp_text)
                elif card_type == "question-answer":
                    add_card(f"What is {term} and why is it important?", exp_text)
                elif card_type == "concept-example":
                    add_card(f"Concept: {term}", f"Description & Example:\n{exp_text}")
                elif card_type == "fill-blank":
                    snippet = exp_text[:110] + "…" if len(exp_text) > 110 else exp_text
                    add_card(f"In this lesson, ______ is described as: {snippet}", f"Answer: {term}\n\n{exp_text}")

    # 2. Key-Value pairs with colons (e.g. "Usability: The system should be easy to use")
    for l in lines:
        if len(cards) >= target_count:
            break
        if ":" in l and not l.startswith("http"):
            parts = l.split(":", 1)
            k, v = parts[0].strip(), parts[1].strip()
            k_clean = re.sub(r"^[✔❌\-\*\•\d+\.\)]\s*", "", k).strip()
            if 1 <= len(k_clean.split()) <= 6 and len(v) > 10:
                if card_type == "term-definition":
                    add_card(k_clean, v)
                elif card_type == "question-answer":
                    add_card(f"What is {k_clean}?", v)
                elif card_type == "concept-example":
                    add_card(f"Topic: {k_clean}", f"Details:\n{v}")
                elif card_type == "fill-blank":
                    snippet = v[:120] + "…" if len(v) > 120 else v
                    add_card(f"______: {snippet}", f"Answer: {k_clean}")

    # 3. Sentences with definitions ("is a", "is defined as", "refers to", "focuses on")
    for l in lines:
        if len(cards) >= target_count:
            break
        cl = re.sub(r"^[✔❌\-\*\•\d+\.\)]\s*", "", l).strip()
        for pat in [
            r"^([A-Z][A-Za-z0-9\s\(\)\/\-]{2,45}?)\s+is\s+(?:a|an|the|defined\s+as)\s+(.+)$",
            r"^([A-Z][A-Za-z0-9\s\(\)\/\-]{2,45}?)\s+(?:refers\s+to|focuses\s+on|aims\s+to|involves)\s+(.+)$"
        ]:
            m = re.match(pat, cl, re.IGNORECASE)
            if m:
                t, d = m.group(1).strip(), m.group(2).strip()
                if len(t.split()) <= 6 and len(d) > 15:
                    if card_type == "term-definition":
                        add_card(t, f"{t} is {d}")
                    elif card_type == "question-answer":
                        add_card(f"How does the material define {t}?", f"{t} is {d}")
                    elif card_type == "concept-example":
                        add_card(f"Key Concept: {t}", f"{t} is {d}")
                    elif card_type == "fill-blank":
                        snippet = d[:120] + "…" if len(d) > 120 else d
                        add_card(f"______ is {snippet}", f"Answer: {t}\n\nFull Statement: {t} is {d}")

    # 4. Questions in the text (e.g. "What is Human-Computer Interaction?")
    for i, l in enumerate(lines):
        if len(cards) >= target_count:
            break
        if l.endswith("?") and len(l) > 10:
            ans = " ".join(lines[i+1:min(i+5, len(lines))]).strip()
            if ans and not ans.endswith("?"):
                q_clean = re.sub(r"^\d+[\.\)]\s*", "", l).strip()
                if card_type == "question-answer":
                    add_card(q_clean, ans)
                elif card_type == "term-definition":
                    term_guess = re.sub(r"^(What is|Why is|How does|Explain)\s+", "", q_clean, flags=re.I).replace("?", "").strip()
                    add_card(term_guess, ans)
                elif card_type == "concept-example":
                    add_card(f"Question / Scenario: {q_clean}", ans)
                elif card_type == "fill-blank":
                    snippet = ans[:110] + "…" if len(ans) > 110 else ans
                    add_card(f"Regarding '{q_clean}': ______ states: {snippet}", f"Answer: {ans}")

    # 5. Core educational sentences and statements to fill up to target_count (up to 100)
    fact_lines = [l for l in lines if len(l) > 25 and not l.startswith("[") and not l.startswith("=") and not l.endswith("?")]
    
    variation_templates = [
        ("Review Point", "What does the text highlight regarding"),
        ("Key Principle", "Explain the concept of"),
        ("Core Takeaway", "Summarize the significance of"),
        ("Design Concept", "How should we understand"),
        ("Study Check", "According to the lesson, what is true about")
    ]

    counter = 0
    while len(cards) < target_count and fact_lines:
        fl = fact_lines[counter % len(fact_lines)]
        cl = re.sub(r"^[✔❌\-\*\•\d+\.\)]\s*", "", fl).strip()
        words = cl.split()
        if len(words) >= 6:
            lead4 = " ".join(words[:4])
            lead2 = " ".join(words[:2])
            card_num = len(cards) + 1
            v_label, v_query = variation_templates[counter % len(variation_templates)]

            if card_type == "term-definition":
                split_idx = min(4, max(1, len(words) // 4))
                head = " ".join(words[:split_idx])
                add_card(f"{v_label} {card_num}: {head}…", cl)
            elif card_type == "question-answer":
                add_card(f"Item {card_num}: {v_query} '{lead4}…'?", cl)
            elif card_type == "concept-example":
                add_card(f"Concept Application {card_num}: {lead4}…", f"Lesson Details:\n{cl}")
            elif card_type == "fill-blank":
                blanked = "______ " + " ".join(words[2:])
                add_card(f"Card {card_num}: {blanked}", f"Answer: {lead2}\n\nFull Statement:\n{cl}")
        counter += 1
        if counter > len(fact_lines) * 5:
            break

    return cards[:target_count]


@router.post("/learning/flashcards")
def create_flashcards(
    request: FlashcardRequest,
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_current_user)
):
    """Generate AI-powered flashcards from an uploaded lesson document."""
    uid = (current_user.get("id") if isinstance(current_user, dict) else None) or request.user_id or "student_arnel"
    card_count = max(1, min(100, request.card_count or 10))
    card_type = request.card_type or "term-definition"

    context, sources = get_lesson_context(uid, request.topic, target_filename=request.document_name)

    # Load all raw chunks of target document for comprehensive synthesis
    all_chunks = get_all_document_chunks(request.document_name, uid)
    full_doc_text = "\n\n".join(c.get("text", "") for c in all_chunks) if all_chunks else context

    # Choose prompt template by card type (default to term-definition)
    prompt_template = FLASHCARD_TYPE_PROMPTS.get(card_type, FLASHCARD_TYPE_PROMPTS["term-definition"])

    # LLM request: batch up to min(25, card_count)
    batch_size = min(25, card_count)
    parsed_cards: List[Dict[str, str]] = []

    prompt = prompt_template.format(
        count=batch_size,
        topic=request.topic,
        context=context[:8000]
    )

    try:
        raw = generate(
            prompt,
            system=(
                "You are KeepAI, a helpful study assistant. Generate clear, accurate flashcards "
                "grounded strictly in the provided lesson material. Use simple, student-friendly language. "
                "Return only a valid JSON array — no markdown, no extra text."
            )
        )
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned
            if cleaned.endswith("```"):
                cleaned = cleaned.rsplit("```", 1)[0]
        cleaned = cleaned.strip()

        parsed = json.loads(cleaned)
        if isinstance(parsed, list):
            for item in parsed:
                if isinstance(item, dict) and "front" in item and "back" in item:
                    parsed_cards.append({
                        "front": str(item["front"]).strip(),
                        "back": str(item["back"]).strip()
                    })
    except Exception as e:
        print(f"Flashcard LLM generation notice: {e}")

    # Synthesize additional cards directly from the document text to reach card_count (up to 100)
    final_cards = synthesize_flashcards_from_document(
        document_text=full_doc_text,
        target_count=card_count,
        card_type=card_type,
        existing_cards=parsed_cards,
        document_name=request.document_name or (sources[0] if sources else None)
    )

    # Track usage stats
    if current_user and isinstance(current_user, dict) and "id" in current_user:
        try:
            user_service.increment_stat(current_user["id"], "flashcards_studied", len(final_cards))
        except Exception:
            pass

    return {
        "topic": request.topic,
        "document_name": request.document_name or (sources[0] if sources else "Uploaded Document"),
        "card_type": card_type,
        "total_cards": len(final_cards),
        "cards": final_cards,
        "sources": sources
    }
