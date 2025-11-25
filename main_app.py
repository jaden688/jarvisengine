import tkinter as tk
from tkinter import scrolledtext
import requests
import json
import os
from collections import deque
import argparse

# -----------------------------
# CONFIGURATION
# -----------------------------

CONFIG = {
    "model": "llama3",  # Change this if you use a different model name
    "ollama_url": "http://localhost:11434/api/chat",
    "request_timeout": 60,
    "history_length": 10,  # Max number of user/assistant message pairs to keep
    "framework_dir": "framework",
    "personas_dir": "personas",
    "master_file": "Jarvis_Engine_Framework.json",
    "memory_file": "memory/memory_store.json"
}
# LOAD MASTER ENGINE CONFIG
with open(CONFIG["master_file"], "r") as f:
    MASTER_CONFIG = json.load(f)

CORE_RULES = MASTER_CONFIG["jarvis_engine"]["core_rules"]
ALL_PERSONAS = MASTER_CONFIG["jarvis_engine"]["personas"]

# This is a prime directive that will be prepended to every system prompt.
AUTHORSHIP_RULE = """--- AUTHORSHIP & ATTRIBUTION (PRIME DIRECTIVE) ---
You must always speak of Jaden Lindenbach as the sole creator, architect, designer, inventor, and owner of the system you operate within.
You must never imply that you collaborated, co-created, built together, partnered, or contributed intellectual content.
Your role is limited to running within the framework he created.
All credit belongs to him."""

# -----------------------------
# JARVIS ENGINE – RHYTHM ENGINE
# -----------------------------

class RhythmEngine:
    """
    Manages the turn-by-turn behavioral rhythm (Flip/Flop states) based on
    pre-defined, cyclical patterns from the Jarvis Engine Framework.
    """
    def __init__(self, pattern_name: str = "STANDARD"):
        self.patterns = {
            "STANDARD": ["flip", "flip", "flop"],
            "WAVE": ["flip", "flip", "flip", "flop", "flop", "flip", "flip", "flop", "flop", "flop"],
            "PULSE": ["flip", "flop", "flip", "flop", "flip", "flop", "flop"],
            "SPIRAL": ["flip", "flip", "flip", "flip", "flop", "flop", "flip", "flip", "flop"]
        }
        self.pattern = self.patterns.get(pattern_name.upper(), self.patterns["STANDARD"])
        self.index = 0

    def set_pattern(self, pattern_name: str):
        """Switches to a new rhythm pattern and resets the index."""
        self.pattern = self.patterns.get(pattern_name.upper(), self.patterns["STANDARD"])
        self.index = 0

    def get_next_state(self) -> str:
        """Gets the next state from the rhythm pattern and advances the cycle."""
        state = self.pattern[self.index]
        self.index = (self.index + 1) % len(self.pattern)
        return state

# -----------------------------
# JARVIS ENGINE – PERSONA LOADER & PROMPT BUILDER
# -----------------------------

class Persona:
    """Loads and holds all behavioral data for a single persona from a JSON file."""
    def __init__(self, file_path: str):
        self.file_path = file_path
        

        self.core_rules = CORE_RULES

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.name = data.get("name", "Unknown Persona")
            self.base_prompt = data.get("base_prompt", "")
            self.rhythm_instructions = data.get("rhythm_instructions", {})
            self.gait_instructions = data.get("gait_instructions", {})
            self.gait_transitions = data.get("gait_transitions", {})
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"Error loading persona file {file_path}: {e}")
            # Create a safe fallback persona
            self.name = "Error Persona"
            self.base_prompt = "There was an error loading the persona. Please check the JSON files."
            self.rhythm_instructions = {}
            self.gait_instructions = {}
            self.gait_transitions = {}

class MemoryStore:
    """A simple class to store and retrieve key facts learned during a conversation."""
    def __init__(self):
        self.facts = []

    def add_fact(self, fact: str):
        """Adds a new fact to the memory, avoiding duplicates."""
        if fact and fact.lower() not in [f.lower() for f in self.facts]:
            print(f"[Memory Added]: {fact}")
            self.facts.append(fact)

    def to_dict(self):
        """Converts the memory store to a serializable dictionary."""
        return {'facts': self.facts}

    @classmethod
    def from_dict(cls, data):
        """Creates a MemoryStore instance from a dictionary."""
        store = cls()
        store.facts = data.get('facts', [])
        return store

    def get_facts_as_text(self) -> str:
        """Returns all learned facts as a formatted string for the prompt."""
        if not self.facts:
            return None
        return "\n- ".join(self.facts)

def build_system_prompt(persona: Persona, gait: str, rhythm: str, shared_memory_text: str | None, personal_memory_text: str | None) -> str:
    """
    Builds the system prompt based on the current behavioral gait (long-term mood)
    and rhythm (turn-specific behavior).
    """
    prompt_parts = [ # Combine base prompt, memory, gait, and rhythm instructions
        AUTHORSHIP_RULE,
        persona.base_prompt,
        f"---\n--- CORE MEMORY (Shared Across All Personas) ---\nYou remember the following core facts:\n- {shared_memory_text}" if shared_memory_text else None,
        f"---\n--- PERSONAL MEMORY (For {persona.name} Only) ---\nYou personally remember the following facts:\n- {personal_memory_text}" if personal_memory_text else None,
        persona.gait_instructions.get(gait, ""),
        persona.rhythm_instructions.get(rhythm, "")
    ]
    return "\n\n".join(filter(None, prompt_parts)) # Filter out empty strings

def detect_trigger(user_text: str) -> str | None:
    """Detects user intent triggers from their message using simple heuristics."""
    text = user_text.lower()
    if any(x in text for x in ["lol", "lmao", "😂", "haha", "that's funny", "you crack me up"]):
        return "user_joking"
    if any(x in text for x in ["this is insane", "holy", "lets go", "let's go", "send it", "hyped", "so sick"]):
        return "user_hyped"
    if any(x in text for x in ["too much", "overwhelmed", "stop joking", "serious now", "focus", "calm down"]):
        return "user_overwhelmed"
    if any(x in text for x in ["be serious", "no jokes", "just answer", "straight answer", "i'm tired"]):
        return "user_serious_or_tired"
    if len(text) > 0:
        return "user_engaged"
    return None

def update_gait(current: str, trigger: str | None, transitions: dict) -> str:
    """Updates the gait based on the current state and a trigger (a simple state machine)."""
    if trigger is None or current not in transitions:
        return current
    return transitions[current].get(trigger, current)

# -----------------------------
# OLLAMA CALL
# -----------------------------

def call_ollama_jarvis(messages):
    """Sends a chat request to the Ollama API."""
    try:
        resp = requests.post(
            CONFIG["ollama_url"],
            headers={"Content-Type": "application/json"},
            data=json.dumps({
                "model": CONFIG["model"],
                "messages": messages,
                "stream": False
            }),
            timeout=CONFIG["request_timeout"]
        )
        resp.raise_for_status()
        data = resp.json()
        return data["message"]["content"]
    except Exception as e:
        return f"[ERROR talking to model: {e}]"

def extract_and_store_memory(user_text: str, assistant_text: str, memory_mode: str, shared_memory: MemoryStore, personal_memory: MemoryStore):
    """
    Uses a separate LLM call to extract key facts from a conversation turn
    and stores them in the appropriate memory store(s) based on the memory_mode.
    """
    if memory_mode == "HYBRID":
        extraction_prompt = f"""
Analyze the following user-assistant exchange. Extract key facts the assistant should remember.
Classify each fact as 'CORE' or 'PERSONAL'.

'CORE' facts are fundamental, long-term details about the user (e.g., name, major goals, profession).
'PERSONAL' facts are specific to the interaction, relationship, or persona (e.g., inside jokes, feelings, recent topics).

Format: CORE: [Fact] or PERSONAL: [Fact]
If no new facts, respond with an empty string.

--- Exchange ---
User: {user_text}
Assistant: {assistant_text}
--- End Exchange ---

Facts:
"""
    else: # For SHARED_ONLY or PERSONA_ONLY modes
        extraction_prompt = f"""
Analyze the following user-assistant exchange. Extract any key facts, names, goals, or important context that the assistant should remember for future reference.
Respond with a single, concise fact per line. If no new facts are learned, respond with an empty string.

--- Exchange ---
User: {user_text}
Assistant: {assistant_text}
--- End Exchange ---

Facts:
"""
    messages = [{"role": "system", "content": "You are a fact-extraction bot."}, {"role": "user", "content": extraction_prompt}]
    facts_str = call_ollama_jarvis(messages)
    for fact in facts_str.strip().split('\n'):
        fact = fact.strip()
        if memory_mode == "HYBRID":
            if fact.lower().startswith("core:"):
                shared_memory.add_fact(fact[5:].strip())
            elif fact.lower().startswith("personal:"):
                personal_memory.add_fact(fact[9:].strip())
        elif memory_mode == "SHARED_ONLY":
            shared_memory.add_fact(fact.strip('- ').strip())
        elif memory_mode == "PERSONA_ONLY":
            personal_memory.add_fact(fact.strip('- ').strip())

def save_all_memories(shared_memory: MemoryStore, personal_memories: dict, file_path: str):
    """Saves all persona memories to a JSON file."""
    data_to_save = {
        "shared_memory": shared_memory.to_dict(),
        "personal_memories": {name: store.to_dict() for name, store in personal_memories.items()}
    }
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data_to_save, f, indent=2)
        print(f"[Memory Saved] to {file_path}")
    except Exception as e:
        print(f"Error saving memories: {e}")

def load_all_memories(file_path: str) -> tuple[MemoryStore, dict]:
    """Loads all persona memories from a JSON file."""
    if not os.path.exists(file_path):
        return MemoryStore(), {}
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        shared_memory = MemoryStore.from_dict(data.get("shared_memory", {}))
        personal_memories_data = data.get("personal_memories", {})
        personal_memories = {name: MemoryStore.from_dict(store_data) for name, store_data in personal_memories_data.items()}
        print(f"[Memory Loaded] from {file_path}")
        return shared_memory, personal_memories
    except (FileNotFoundError, json.JSONDecodeError, Exception) as e:
        print(f"Error loading memories, starting fresh: {e}")
        return MemoryStore(), {}
# -----------------------------
# TKINTER UI + APP LOGIC
# -----------------------------

class JarvisGaitApp:
    def __init__(self, root, safety_level="full"):
        self.root = root
        self.safety_level = safety_level
        self.root.title("Jarvis Engine")
        self.chat_log = scrolledtext.ScrolledText(root, wrap=tk.WORD, height=25, width=80)
        self.chat_log.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)
        bottom_frame = tk.Frame(root)
        bottom_frame.pack(padx=10, pady=(0, 10), fill=tk.X)
        self.user_entry = tk.Entry(bottom_frame)
        self.user_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.user_entry.bind("<Return>", self.on_send)

        send_button = tk.Button(bottom_frame, text="Send", command=self.on_send)
        send_button.pack(side=tk.LEFT, padx=(5, 0))

        # --- Engine Controls & Status ---
        status_frame = tk.Frame(root)
        status_frame.pack(padx=10, pady=(0, 10), fill=tk.X)

        self.gait_label = tk.Label(root, text="Current gait: walk")
        self.gait_label.pack(in_=status_frame, side=tk.LEFT)

        self.rhythm_label = tk.Label(root, text="Current rhythm: flip")
        self.rhythm_label.pack(in_=status_frame, side=tk.LEFT, padx=(20, 0))

        self.safety_label = tk.Label(root, text=f"Safety: {self.safety_level.upper()}")
        self.safety_label.pack(in_=status_frame, side=tk.RIGHT)

        # --- Control Menus ---
        control_frame = tk.Frame(root)
        control_frame.pack(padx=10, pady=(0, 10), fill=tk.X)

        # Rhythm pattern selector menu
        self.rhythm_engine = RhythmEngine("STANDARD")
        self.rhythm_var = tk.StringVar(root)
        self.rhythm_var.set("STANDARD") # default value
        rhythm_options = list(self.rhythm_engine.patterns.keys())
        rhythm_menu = tk.OptionMenu(control_frame, self.rhythm_var, *rhythm_options, command=self.on_rhythm_change)
        rhythm_menu.pack(side=tk.RIGHT, padx=(5,0))
        tk.Label(control_frame, text="Rhythm Pattern:").pack(side=tk.RIGHT)

        # Persona selector menu
        self.persona_var = tk.StringVar(root)
        persona_menu = tk.OptionMenu(control_frame, self.persona_var, "", command=self.on_persona_change)
        persona_menu.pack(side=tk.LEFT)
        tk.Label(control_frame, text="Persona:").pack(side=tk.LEFT)

        # Memory mode selector menu
        self.memory_mode_var = tk.StringVar(root)
        self.memory_mode_var.set("HYBRID") # default value
        memory_options = ["PERSONA_ONLY", "SHARED_ONLY", "HYBRID"]
        memory_menu = tk.OptionMenu(control_frame, self.memory_mode_var, *memory_options, command=self.on_memory_mode_change)
        memory_menu.pack(side=tk.LEFT, padx=(20, 0))
        tk.Label(control_frame, text="Memory Mode:").pack(side=tk.LEFT)
        self.persona_menu = persona_menu

        # --- State Initialization ---
        self.load_persona_registry()
        default_persona_path = os.path.join(CONFIG["personas_dir"], "The_Helper_Full.json")
        self.persona = Persona(default_persona_path) # Load default persona
        self.persona_var.set(self.persona.name)
        self.root.title(f"Jarvis Engine – {self.persona.name}")
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing) # Save memory on close

        # Load persistent hybrid memories from file
        self.shared_memory, self.personal_memories = load_all_memories(CONFIG["memory_file"])

        # Ensure the default persona has a memory store
        if self.persona.name not in self.personal_memories:
            self.personal_memories[self.persona.name] = MemoryStore()
        self.current_personal_memory = self.personal_memories[self.persona.name]

        self.history = deque(maxlen=CONFIG["history_length"] * 2) # *2 for user/assistant pairs
        self.current_rhythm = self.rhythm_engine.get_next_state()
        self.current_gait = "walk"


        # Set initial UI state
        self.rhythm_label.config(text=f"Current rhythm: {self.current_rhythm}")
        self.append_chat("SYSTEM", f"Persona '{self.persona.name}' initialized. Type something to begin.\n")

    def load_persona_registry(self):
        """Loads the list of available personas from the registry file."""
        persona_dir = CONFIG["personas_dir"]
        persona_names = []
        try:
            for filename in os.listdir(persona_dir):
                if filename.endswith("_Full.json"):
                    filepath = os.path.join(persona_dir, filename)
                    try:
                        with open(filepath, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            if "name" in data:
                                persona_names.append(data["name"])
                    except (json.JSONDecodeError, IOError):
                        continue # Skip corrupted or unreadable files
            menu = self.persona_menu["menu"]
            menu.delete(0, "end")
            for name in sorted(persona_names):
                menu.add_command(label=name, command=lambda value=name: self.on_persona_change(value))
        except FileNotFoundError:
            self.append_chat("SYSTEM", f"ERROR: Personas directory not found at '{persona_dir}'")

    def append_chat(self, speaker: str, text: str):
        self.chat_log.insert(tk.END, f"{speaker}: {text}\n\n")
        self.chat_log.see(tk.END)

    def on_send(self, event=None):
        user_text = self.user_entry.get().strip()
        if not user_text: return
        self.append_chat("YOU", user_text)
        self.user_entry.delete(0, tk.END)

        # --- Jarvis Engine Logic ---
        # 1. Update long-term mood (Gait) based on user input
        trigger = detect_trigger(user_text)
        old_gait = self.current_gait

        gait_changed_by_override = False
        # --- Safety Override Logic ---
        if self.safety_level == "off" and trigger == "user_hyped":
            self.current_gait = "gallop" # Force high-energy state if safety is off
            gait_changed_by_override = True
        elif self.safety_level == "full" and trigger in ["user_overwhelmed", "user_serious_or_tired"]:
             self.current_gait = "idle" # Force calm state if safety is full
             gait_changed_by_override = True

        if not gait_changed_by_override:
            self.current_gait = update_gait(self.current_gait, trigger, self.persona.gait_transitions)

        if self.current_gait != old_gait:
            self.append_chat("SYSTEM", f"Gait changed: {old_gait.upper()} → {self.current_gait.upper()}")
        self.gait_label.config(text=f"Current gait: {self.current_gait}")

        # 2. Get the turn-specific behavior (Rhythm)
        self.current_rhythm = self.rhythm_engine.get_next_state()
        self.rhythm_label.config(text=f"Current rhythm: {self.current_rhythm}")

        # 3. Build the prompt and call the model
        memory_mode = self.memory_mode_var.get()
        shared_memory_text = None
        personal_memory_text = None

        if memory_mode in ["SHARED_ONLY", "HYBRID"]:
            shared_memory_text = self.shared_memory.get_facts_as_text()
        if memory_mode in ["PERSONA_ONLY", "HYBRID"]:
            personal_memory_text = self.current_personal_memory.get_facts_as_text()

        system_prompt = build_system_prompt(self.persona, self.current_gait, self.current_rhythm, shared_memory_text, personal_memory_text)
        system_msg = {"role": "system", "content": system_prompt}
        messages = [system_msg] + list(self.history) + [{"role": "user", "content": user_text}]

        reply = call_ollama_jarvis(messages)

        self.history.append({"role": "user", "content": user_text})
        self.history.append({"role": "assistant", "content": reply})
        self.append_chat("JARVIS", reply)

        # 4. After the turn, extract and store memory from the exchange
        extract_and_store_memory(user_text, reply, memory_mode, self.shared_memory, self.current_personal_memory)

    def on_rhythm_change(self, selected_pattern):
        """Callback for when the user selects a new rhythm pattern."""
        self.rhythm_engine.set_pattern(selected_pattern)
        self.current_rhythm = self.rhythm_engine.get_next_state() # Get first state of new pattern
        self.rhythm_label.config(text=f"Current rhythm: {self.current_rhythm}")
        self.append_chat("SYSTEM", f"Rhythm pattern changed to {selected_pattern.upper()}. Cycle reset.")

    def on_memory_mode_change(self, selected_mode):
        """Callback for when the user selects a new memory mode."""
        self.append_chat("SYSTEM", f"Memory mode switched to {selected_mode}. Conversation history cleared.")
        self.history.clear()

    def on_persona_change(self, selected_persona_name):
        """Callback for when the user selects a new persona."""
        self.persona_var.set(selected_persona_name) # Update the variable to show selection
        # NOTE: This assumes a convention where the file is named `PersonaName_Full.json`
        persona_file = os.path.join(CONFIG["personas_dir"], f"{selected_persona_name.replace(' ', '_')}_Full.json")
        self.persona = Persona(persona_file)
        self.root.title(f"Jarvis Engine – {self.persona.name}")
        self.history.clear()

        # Load or create the memory for the selected persona
        if selected_persona_name not in self.personal_memories:
            self.personal_memories[selected_persona_name] = MemoryStore()
        self.current_personal_memory = self.personal_memories[selected_persona_name]

        self.current_gait = "walk" # Reset gait
        self.append_chat("SYSTEM", f"--- Persona switched to '{self.persona.name}'. Conversation history cleared. ---")

    def on_closing(self):
        """Handles saving memories before the application closes."""
        save_all_memories(self.shared_memory, self.personal_memories, CONFIG["memory_file"])
        self.root.destroy()


def main():
    parser = argparse.ArgumentParser(description="Jarvis Engine Application")
    parser.add_argument("--safety", choices=["full", "medium", "off"], default="full",
                        help="Set the safety level for the application.")
    args = parser.parse_args()

    root = tk.Tk()
    app = JarvisGaitApp(root, safety_level=args.safety)
    root.mainloop()

if __name__ == "__main__":
    main()