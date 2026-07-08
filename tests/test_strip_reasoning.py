"""Tests for _strip_reasoning - verifies leaked reasoning tags are stripped."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".ella"))
from agent import _strip_reasoning

# Build XML tags programmatically to avoid tool mangling
T = "\x3cthink\x3e"
TC = "\x3c/think\x3e"
MM = "\x3cmm:think\x3e"
MMC = "\x3c/mm:think\x3e"
SEED = "\x3cseed:think\x3e"
SEEDC = "\x3c/seed:think\x3e"
ANS = "\x3canswer\x3e"
ANSC = "\x3c/answer\x3e"
RESP = "\x3cresponse\x3e"
RESPC = "\x3c/response\x3e"


class TestStripReasoningXMLThink:
    """XML-style think tags (DeepSeek R1, Qwen3, GLM, etc.)"""

    def test_deepseek_closed_block(self):
        text = f"{T}reasoning here{TC}\nThe fix works!"
        assert _strip_reasoning(text).strip() == "The fix works!"

    def test_deepseek_multiline(self):
        text = f"{T}\nLet me analyze this step by step.\nFirst, I check the bug.\n{TC}\nDone!"
        assert _strip_reasoning(text).strip() == "Done!"

    def test_qwen_closed_block(self):
        text = f"{T}thinking\n{TC}Here is my answer."
        assert _strip_reasoning(text).strip() == "Here is my answer."

    def test_only_closing_tag(self):
        """Model pre-filled reasoning externally, only emits closing tag."""
        text = f"{TC}\nHere is the actual response."
        assert _strip_reasoning(text).strip() == "Here is the actual response."

    def test_unclosed_think_strips_all(self):
        """If opening tag leaks but no closing tag, strip everything after it."""
        text = f"{T}Let me work on this... and it keeps going"
        assert _strip_reasoning(text).strip() == ""

    def test_hunyuan_think_then_answer(self):
        text = f"{T}reasoning\n{TC}\n{ANS}The real answer{ANSC}"
        assert _strip_reasoning(text).strip() == "The real answer"

    def test_ernie_think_then_response(self):
        text = f"{T}thinking\n{TC}\n{RESP}Here is my reply{RESPC}"
        assert _strip_reasoning(text).strip() == "Here is my reply"

    def test_minimax_mm_think(self):
        text = f"{MM}thinking\n{MMC}\ncontent here"
        assert _strip_reasoning(text).strip() == "content here"

    def test_seedoss(self):
        text = f"{SEED}reasoning\n{SEEDC}\nReply text."
        assert _strip_reasoning(text).strip() == "Reply text."


class TestStripReasoningSpecialTokens:
    """Non-XML special token variants"""

    def test_mistral_think_brackets(self):
        text = "[THINK]reasoning here[/THINK]\nThe answer is 42."
        assert _strip_reasoning(text).strip() == "The answer is 42."

    def test_mistral_only_close_bracket(self):
        text = "[/THINK]\nThe answer is 42."
        assert _strip_reasoning(text).strip() == "The answer is 42."

    def test_cohere_pipes(self):
        text = "<|START_THINKING|>analyzing<|END_THINKING|>\nDone!"
        assert _strip_reasoning(text).strip() == "Done!"

    def test_cohere_unclosed(self):
        text = "<|START_THINKING|>analyzing and it keeps going"
        assert _strip_reasoning(text).strip() == ""

    def test_kimi_unicode(self):
        # U+25C1=◁, U+25B7=▷ (White Left/Right-pointing Triangle)
        text = "\u25c1think\u25b7reasoning\u25c1/think\u25b7\nAnswer."
        assert _strip_reasoning(text).strip() == "Answer."

    def test_gemma_channel(self):
        text = "<|channel>thought\nreasoning<channel|>\nFinal answer."
        assert _strip_reasoning(text).strip() == "Final answer."

    def test_gpt_oss_analysis(self):
        text = "<|channel|>analysis\nthinking<|end|>\nResponse."
        assert _strip_reasoning(text).strip() == "Response."


class TestStripReasoningEdgeCases:
    def test_no_reasoning(self):
        text = "Just a normal message."
        assert _strip_reasoning(text).strip() == "Just a normal message."

    def test_empty_string(self):
        assert _strip_reasoning("") == ""

    def test_whitespace_only(self):
        assert _strip_reasoning("   \n  ") == ""

    def test_think_in_word(self):
        """Should not match 'think' inside a normal word (needs angle brackets)."""
        text = "I think this is the answer."
        assert _strip_reasoning(text).strip() == "I think this is the answer."

    def test_multiple_reasoning_blocks(self):
        text = f"{T}first reasoning{TC}\nPart 1\n{T}second reasoning{TC}\nPart 2"
        assert _strip_reasoning(text).strip() == "Part 1\nPart 2"

    def test_answer_without_think(self):
        """Answer tag with no preceding think - just unwrap the content."""
        text = f"{ANS}Final answer here{ANSC}"
        assert _strip_reasoning(text).strip() == "Final answer here"

    def test_response_without_think(self):
        text = f"{RESP}Here is my reply{RESPC}"
        assert _strip_reasoning(text).strip() == "Here is my reply"
