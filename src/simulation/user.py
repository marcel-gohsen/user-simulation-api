import abc
import copy
import json
import logging
from typing import List, Dict, Any, Tuple, Optional

import torch
from sentence_transformers import SentenceTransformer

import config
from data.topic import Topic
from simulation.llm import HFModelQuantized, LLMVersion, Precision, OpenAIModelVersion, OpenAIModel


class User(metaclass=abc.ABCMeta):

    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.setLevel(logging.DEBUG)

    @abc.abstractmethod
    def initiate(self, topic_id: str) -> str:
        pass

    @abc.abstractmethod
    def respond(self, topic_id, subtopics: List[str], messages: List[Dict[str, Any]]) -> Tuple[str, Optional[str], Optional[int]]:
        pass


class PTKBUserWithGuidance(User):
    llm = HFModelQuantized(LLMVersion.Gemma_3_4B_IT, quantization=Precision.NF4)
    st_model = SentenceTransformer("all-mpnet-base-v2")

    base_prompt = ("You are a user of a search system and are interested in \"{topic}\". "
                   "Your goal is to find out as much as possible about the topic. "
                   "Ask short questions and interact with the system. Respond with a single utterance only. "
                   "Don't ever repeat information in the dialog."
                   "\n\nYou have the following properties:\n- {property_list}")

    gen_kwargs = {"max_new_tokens": 128, "num_return_sequences":5, "num_beam_groups":5,
                  "num_beams":10, "early_stopping": True, "do_sample": False,
                  "diversity_penalty": 8.0, "top_k": None, "top_p": None}

    answer_rating_prompt = ("Can the question be answered based on the available context? Pick from the numbers below.\n"
                          "5: The answer is highly relevant, complete, and accurate.\n"
                          "4: The answer is mostly relevant and complete but may have minor gaps or inaccuracies.\n"
                          "3: The answer is partially relevant and complete, with noticeable gaps or inaccuracies.\n"
                          "2: The answer has limited relevance and completeness, with significant gaps or inaccuracies.\n"
                          "1: The answer is minimally relevant or complete, with substantial shortcomings.\n"
                          "0: The answer is not relevant or complete at all.\n"
                          "Question: {subtopic}\n"
                          "Context: {answer}")

    answer_rating_gen_kwargs = {"do_sample": False, "max_new_tokens": 1, "top_p": None, "top_k": None}

    def __init__(self, _id, topics: Dict[str, Topic], subtopics: Dict[str, List[str]], ptkb: List[str]):
        super().__init__()
        self._id = _id
        self.topics = topics
        self.subtopics = subtopics
        self.ptkb = ptkb

    def initiate(self, topic_id: str) -> Tuple[str, str]:
        topic = self.topics[topic_id]
        subtopics = self.subtopics[topic_id]
        next_subtopic = subtopics[0]
        self.logger.debug(f"Next subtopic: {next_subtopic}.")

        init_system_prompt = self.base_prompt.format(topic=topic.title.lower(), property_list="\n- ".join(self.ptkb))

        messages = [
            {"role": "system", "content": init_system_prompt + f"\n\nExplore the following question:\n\"{next_subtopic}\""},
            {"role": "user", "content": f"How may I help you?"},
        ]

        best_response = self.conditional_response_generation(messages, next_subtopic)
        return best_response, next_subtopic

    def respond(self, topic_id: str, subtopics: List[str], messages: List[Dict[str, Any]]) -> Tuple[str, Optional[str], Optional[int]]:
        topic = self.topics[topic_id]

        assistant_response = messages[-1]["content"]
        self.logger.debug(f"Assistant response: {assistant_response}")
        init_system_prompt = self.base_prompt.format(topic=topic.title.lower(),
                                                     property_list="\n- ".join(self.ptkb))

        new_messages = copy.deepcopy(messages)
        for m in new_messages:
            if m["role"] == "user":
                m["role"] = "assistant"
            elif m["role"] == "assistant":
                m["role"] = "user"

        new_messages = [{"role": "system", "content": init_system_prompt},
                        {"role": "user", "content": "How can I help you?"},
                        *new_messages]
        answer_rating = self.get_answer_rating(subtopics[-1], assistant_response)
        if answer_rating is not None and answer_rating > config.CONFIG["simulation"]["rubric_threshold"]:
            # Answer was satisfactory
            next_subtopic = self.pick_next_subtopic(topic_id, subtopics)

            if next_subtopic is None:
                new_messages[0]["content"] \
                    = f"You gathered all necessary information. Say thank you and farewell."
                response = self.llm.generate(new_messages)[0]

                return response, None, answer_rating

            new_messages[0]["content"] += f"\n\nYou are satisfied with the last given answer. Now, explore the following question \"{next_subtopic}\"."
        else:
            # Answer was not satisfactory or grading failed
            if subtopics.count(subtopics[-1]) >= config.CONFIG["simulation"]["num_retries"]:
                next_subtopic = self.pick_next_subtopic(topic_id, subtopics)

                if next_subtopic is None:
                    new_messages[0]["content"] \
                        = "You gathered all necessary information. Say thank you and farewell."
                    response = self.llm.generate(new_messages)[0]

                    return response, None, answer_rating

                new_messages[0]["content"] \
                    += f"\n\nThe last given answer was not helpful but you continue anyway. Now explore the following question \"{next_subtopic}\"."

            else:
                if answer_rating is None:
                    # Grading failed
                    new_messages[0]["content"] \
                        += f"\n\nYou did not fully understand the answer. Ask for clarification on the last response."
                else:
                    # Answer was not satisfactory and maximum attempts is not reached
                    new_messages[0]["content"] \
                        += f"\n\nThe last given answer was not helpful. Inform the system about that. Ask more specifically about the following question \"{subtopics[-1]}\"."

                next_subtopic = subtopics[-1]

        best_response = self.conditional_response_generation(new_messages, next_subtopic)
        return best_response, next_subtopic, answer_rating



    def get_answer_rating(self, subtopic: str, answer: str) -> Optional[int]:
        rating = self.llm.generate([
            {"role": "user", "content": self.answer_rating_prompt.format(answer=answer,subtopic=subtopic)}
        ], **self.answer_rating_gen_kwargs)[0]

        self.logger.debug(f"Answer rating: {rating}")
        try:
            rating = int(rating)
        except ValueError:
            return None

        return rating

    def pick_next_subtopic(self, topic_id: str, subtopic_history: List[str]) -> Optional[str]:
        open_subtopics = [s for s in self.subtopics[topic_id] if s not in subtopic_history]

        if len(open_subtopics) == 0:
            return None

        # choice = random.choice(open_subtopics)
        choice = open_subtopics[0]
        self.logger.debug(f"Next subtopic: {choice}")
        return choice


    def conditional_response_generation(self, messages: List[Dict[str, Any]], subtopic:str) -> str:
        self.logger.debug(f"Generate: {json.dumps(messages)}")
        responses = self.llm.generate(messages, **self.gen_kwargs)
        self.logger.debug(f"Response candidates: {responses}")

        texts = [subtopic, *responses]
        encodings = self.st_model.encode(texts, show_progress_bar=False)
        similarities = self.st_model.similarity(encodings, encodings)
        indices = torch.argsort(similarities, dim=1, descending=True)
        best_response = responses[indices[0][1] - 1]
        self.logger.debug(f"Best response: {best_response}")

        return best_response


class PTKBUserWithoutGuidance(User):
    llm = HFModelQuantized(LLMVersion.Gemma_3_4B_IT, quantization=Precision.NF4)

    base_prompt = ("You are a user of a search system and are interested in \"{topic}\". "
                   "Your goal is to find out as much as possible about the topic. "
                   "Ask short questions and interact with the system. Respond with a single utterance only. "
                   "Don't ever repeat information in the dialog."
                   "\n\nYou have the following properties:\n- {property_list}")

    gen_kwargs = {"max_new_tokens": 128, "num_return_sequences":5, "num_beam_groups":5,
                  "num_beams":10, "early_stopping": True, "do_sample": False,
                  "diversity_penalty": 8.0, "top_k": None, "top_p": None}

    def __init__(self, _id, topics: Dict[str, Topic], subtopics: Dict[str, List[str]], ptkb: List[str]):
        super().__init__()
        self._id = _id
        self.topics = topics
        self.subtopics = subtopics
        self.ptkb = ptkb

    def initiate(self, topic_id: str) -> Tuple[str, Optional[str]]:
        topic = self.topics[topic_id]

        init_system_prompt = self.base_prompt.format(topic=topic.title.lower(), property_list="\n- ".join(self.ptkb))

        messages = [
            {"role": "system", "content": init_system_prompt},
            {"role": "user", "content": f"How may I help you?"},
        ]

        best_response = self.conditional_response_generation(messages)
        return best_response, ""

    def respond(self, topic_id: str, subtopics: List[str], messages: List[Dict[str, Any]]) -> Tuple[str, Optional[str], Optional[int]]:
        topic = self.topics[topic_id]

        assistant_response = messages[-1]["content"]
        self.logger.debug(f"Assistant response: {assistant_response}")
        init_system_prompt = self.base_prompt.format(topic=topic.title.lower(),
                                                     property_list="\n- ".join(self.ptkb))

        new_messages = copy.deepcopy(messages)
        for m in new_messages:
            if m["role"] == "user":
                m["role"] = "assistant"
            elif m["role"] == "assistant":
                m["role"] = "user"

        num_user_messages = len([m for m in new_messages if m["role"] == "user"])
        if num_user_messages >= len(self.subtopics[topic_id]):
            new_messages = [{"role": "system", "content": init_system_prompt},
                            {"role": "user", "content": "How can I help you?"},
                            *new_messages]

            new_messages[0]["content"] \
                = f"You gathered all necessary information. Say thank you and farewell."
            response = self.llm.generate(new_messages)[0]

            return response, None, None

        new_messages = [{"role": "system", "content": init_system_prompt},
                        {"role": "user", "content": "How can I help you?"},
                        *new_messages]

        best_response = self.conditional_response_generation(new_messages)
        return best_response, "", None


    def conditional_response_generation(self, messages: List[Dict[str, Any]]) -> str:
        self.logger.debug(f"Generate: {json.dumps(messages)}")
        responses = self.llm.generate(messages, **self.gen_kwargs)
        self.logger.debug(f"Response candidates: {responses}")

        best_response = responses[0]
        self.logger.debug(f"Best response: {best_response}")

        return best_response


class OpenAIPTKBUserWithGuidance(PTKBUserWithGuidance):
    llm = OpenAIModel(OpenAIModelVersion.GPT_4_1)

    base_prompt = ("You are a user of a search system and are interested in \"{topic}\". "
                   "Your goal is to find out as much as possible about the topic. "
                   "Ask short questions and interact with the system. Respond with short utterances only. "
                   "Be vague about the questions, provide feedback, and ask follow up questions. "
                   "Answer question when you get asked some. "
                   "Don't ever repeat information in the dialog. "
                   "You should behave according to the list of given properties below. "
                   "Reveal properties when you think it is necessary but don't give out the whole list. "
                   "\n\nYou have the following properties:\n- {property_list}")

    gen_kwargs = {"max_completion_tokens": 128, "n": 5}

    answer_rating_prompt = (
        "Can the question be answered based on the available context? Pick from the numbers below.\n"
        "5: The answer is highly relevant, complete, and accurate.\n"
        "4: The answer is mostly relevant and complete but may have minor gaps or inaccuracies.\n"
        "3: The answer is partially relevant and complete, with noticeable gaps or inaccuracies.\n"
        "2: The answer has limited relevance and completeness, with significant gaps or inaccuracies.\n"
        "1: The answer is minimally relevant or complete, with substantial shortcomings.\n"
        "0: The answer is not relevant or complete at all.\n\n"
        "Question: {subtopic}\n"
        "Context: {answer}\n"
        "Number: ")

    answer_rating_gen_kwargs = {"max_completion_tokens": 1, "n": 1}


class OpenAIPTKBUserWithoutGuidance(PTKBUserWithoutGuidance):
    llm = OpenAIModel(OpenAIModelVersion.GPT_4_1)

    base_prompt = ("You are a user of a search system and are interested in \"{topic}\". "
                   "Your goal is to find out as much as possible about the topic. "
                   "Ask short questions and interact with the system. Respond with short utterances only. "
                   "Be vague about the questions, provide feedback, and ask follow up questions. "
                   "Answer question when you get asked some. "
                   "Don't ever repeat information in the dialog. "
                   "You should behave according to the list of given properties below. "
                   "Reveal properties when you think it is necessary but don't give out the whole list. "
                   "\n\nYou have the following properties:\n- {property_list}")

    gen_kwargs = {"max_completion_tokens": 128, "n": 5}


