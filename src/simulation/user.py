import abc
import copy
import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

import torch
from sentence_transformers import SentenceTransformer

import config
from shared_task.sessions import Session
from shared_task.topic import Topic

from simulation.llm import HFModelQuantized, LLMVersion, Precision, OpenAIModelVersion, OpenAIModel


@dataclass
class UserUtterance:
    content: str

    end_of_session: bool

    meta: Dict[str, Any] = field(default_factory=dict)


class User(metaclass=abc.ABCMeta):

    def __init__(self, _id, topics: Dict[str, Topic]):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.setLevel(logging.DEBUG)
        self.id = _id
        self.topics = topics

    @abc.abstractmethod
    def initiate(self, session: Session) -> UserUtterance:
        pass

    @abc.abstractmethod
    def respond(self, session: Session) -> UserUtterance:
        pass


class DummyUser(User):

    def __init__(self, topics: Dict[str, Topic]):
        super().__init__(uuid.uuid4().hex, topics)

    def initiate(self, session: Session) -> UserUtterance:
        return UserUtterance(
            content=self.topics[session.topic_id].title,
            end_of_session=False
        )

    def respond(self, session: Session) -> UserUtterance:
        return UserUtterance(
            content="Thanks for your response!",
            end_of_session=True
        )


class PlanningBasedUserSimulator(User):
    llm = None
    st_model = None

    base_prompt = ("You are a user of a search system and are interested in \"{topic}\". "
                   "Your goal is to find out as much as possible about the topic. "
                   "Ask short questions and interact with the system. Respond with a single utterance only. "
                   "Don't ever repeat information in the dialog."
                   "\n\nYou have the following properties:\n- {property_list}")

    gen_kwargs = {"max_new_tokens": 128, "num_return_sequences":5, "num_beam_groups":5,
                  "num_beams":10, "early_stopping": True, "do_sample": False,
                  "diversity_penalty": 8.0, "top_k": None, "top_p": None}

    rubric_score_prompt = ("Can the question be answered based on the available context? Pick from the numbers below.\n"
                          "5: The answer is highly relevant, complete, and accurate.\n"
                          "4: The answer is mostly relevant and complete but may have minor gaps or inaccuracies.\n"
                          "3: The answer is partially relevant and complete, with noticeable gaps or inaccuracies.\n"
                          "2: The answer has limited relevance and completeness, with significant gaps or inaccuracies.\n"
                          "1: The answer is minimally relevant or complete, with substantial shortcomings.\n"
                          "0: The answer is not relevant or complete at all.\n"
                          "Question: {subtopic}\n"
                          "Context: {answer}")

    rubric_score_gen_kwargs = {"do_sample": False, "max_new_tokens": 1, "top_p": None, "top_k": None}

    def __init__(self, _id, topics: Dict[str, Topic], rubrics: Dict[str, List[str]], ptkb: List[str]):
        super().__init__(_id, topics)
        self.rubrics = rubrics
        self.ptkb = ptkb

        if PlanningBasedUserSimulator.llm is None:
            PlanningBasedUserSimulator.llm = HFModelQuantized(LLMVersion.Gemma_3_4B_IT, quantization=Precision.NF4)

        if PlanningBasedUserSimulator.st_model is None:
            PlanningBasedUserSimulator.st_model = SentenceTransformer("all-mpnet-base-v2")

    def initiate(self, session: Session) -> UserUtterance:
        topic = self.topics[session.topic_id]
        rubrics = self.rubrics[session.topic_id]
        next_rubric = rubrics[0]
        self.logger.debug(f"Next rubric question: {next_rubric}.")

        init_system_prompt = self.base_prompt.format(topic=topic.title.lower(), property_list="\n- ".join(self.ptkb))

        messages = [
            {"role": "system", "content": init_system_prompt + f"\n\nExplore the following question:\n\"{next_rubric}\""},
            {"role": "user", "content": f"How may I help you?"},
        ]

        best_response = self.conditional_response_generation(messages, next_rubric)
        return UserUtterance(
            best_response,
            False,
            {"rubric": next_rubric},
        )

    def respond(self, session: Session) -> UserUtterance:
        topic = self.topics[session.topic_id]

        assistant_response = session.history[-1]["content"]
        self.logger.debug(f"Assistant response: {assistant_response}")
        init_system_prompt = self.base_prompt.format(topic=topic.title.lower(),
                                                     property_list="\n- ".join(self.ptkb))

        new_messages = copy.deepcopy(session.history)
        for m in new_messages:
            if m["role"] == "user":
                m["role"] = "assistant"
            elif m["role"] == "assistant":
                m["role"] = "user"

        new_messages = [{"role": "system", "content": init_system_prompt},
                        {"role": "user", "content": "How can I help you?"},
                        *new_messages]
        rubric_score = self.get_rubric_score(session.user_meta[-1]["rubric"], assistant_response)
        rubric_history = [m["rubric"] for m in session.user_meta]
        if rubric_score is not None and rubric_score > config.CONFIG["simulation"]["rubric_threshold"]:
            # Answer was satisfactory
            next_rubric = self.select_next_rubric(session.topic_id, rubric_history)

            if next_rubric is None:
                new_messages[0]["content"] \
                    = f"You gathered all necessary information. Say thank you and farewell."
                response = self.llm.generate(new_messages)[0]


                return UserUtterance(
                    response,
                    True,
                    {"rubric_score": rubric_score}
                )

            new_messages[0]["content"] += f"\n\nYou are satisfied with the last given answer. Now, explore the following question \"{next_rubric}\"."
        else:
            # Answer was not satisfactory or grading failed
            if rubric_history.count(rubric_history[-1]) >= config.CONFIG["simulation"]["num_retries"]:
                next_rubric = self.select_next_rubric(session.topic_id, rubric_history)

                if next_rubric is None:
                    new_messages[0]["content"] \
                        = "You gathered all necessary information. Say thank you and farewell."
                    response = self.llm.generate(new_messages)[0]

                    return UserUtterance(
                        response,
                        True,
                        {"rubric_score": rubric_score}
                    )

                new_messages[0]["content"] \
                    += f"\n\nThe last given answer was not helpful but you continue anyway. Now explore the following question \"{next_rubric}\"."

            else:
                if rubric_score is None:
                    # Grading failed
                    new_messages[0]["content"] \
                        += f"\n\nYou did not fully understand the answer. Ask for clarification on the last response."
                else:
                    # Answer was not satisfactory and maximum attempts is not reached
                    new_messages[0]["content"] \
                        += f"\n\nThe last given answer was not helpful. Inform the system about that. Ask more specifically about the following question \"{rubric_history[-1]}\"."

                next_rubric = rubric_history[-1]

        best_response = self.conditional_response_generation(new_messages, next_rubric)
        return UserUtterance(
            best_response,
            False,
            {"rubric_score": rubric_score, "rubric": next_rubric}
        )



    def get_rubric_score(self, rubric: str, response: str) -> Optional[int]:
        rating = self.llm.generate([
            {"role": "user", "content": self.rubric_score_prompt.format(answer=response, subtopic=rubric)}
        ], **self.rubric_score_gen_kwargs)[0]

        self.logger.debug(f"Answer rating: {rating}")
        try:
            rating = int(rating)
        except ValueError:
            return None

        return rating

    def select_next_rubric(self, topic_id: str, rubric_history: List[str]) -> Optional[str]:
        open_subtopics = [s for s in self.rubrics[topic_id] if s not in rubric_history]

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


class UnrestrictedUserSimulator(User):
    llm = None

    base_prompt = ("You are a user of a search system and are interested in \"{topic}\". "
                   "Your goal is to find out as much as possible about the topic. "
                   "Ask short questions and interact with the system. Respond with a single utterance only. "
                   "Don't ever repeat information in the dialog."
                   "\n\nYou have the following properties:\n- {property_list}")

    gen_kwargs = {"max_new_tokens": 128, "num_return_sequences":5, "num_beam_groups":5,
                  "num_beams":10, "early_stopping": True, "do_sample": False,
                  "diversity_penalty": 8.0, "top_k": None, "top_p": None}

    def __init__(self, _id, topics: Dict[str, Topic], rubrics: Dict[str, List[str]], ptkb: List[str]):
        super().__init__(_id, topics)
        self.rubrics = rubrics
        self.ptkb = ptkb

        if PlanningBasedUserSimulator.llm is None:
            PlanningBasedUserSimulator.llm = HFModelQuantized(LLMVersion.Gemma_3_4B_IT, quantization=Precision.NF4)

        if PlanningBasedUserSimulator.st_model is None:
            PlanningBasedUserSimulator.st_model = SentenceTransformer("all-mpnet-base-v2")

    def initiate(self, session: Session) -> UserUtterance:
        topic = self.topics[session.topic_id]

        init_system_prompt = self.base_prompt.format(topic=topic.title.lower(), property_list="\n- ".join(self.ptkb))

        messages = [
            {"role": "system", "content": init_system_prompt},
            {"role": "user", "content": f"How may I help you?"},
        ]

        best_response = self.conditional_response_generation(messages)
        return UserUtterance(
            best_response,
            False
        )

    def respond(self, session: Session) -> UserUtterance:
        topic = self.topics[session.topic_id]

        assistant_response = session.history[-1]["content"]
        self.logger.debug(f"Assistant response: {assistant_response}")
        init_system_prompt = self.base_prompt.format(topic=topic.title.lower(),
                                                     property_list="\n- ".join(self.ptkb))

        new_messages = copy.deepcopy(session.history)
        for m in new_messages:
            if m["role"] == "user":
                m["role"] = "assistant"
            elif m["role"] == "assistant":
                m["role"] = "user"

        num_user_messages = len([m for m in new_messages if m["role"] == "user"])
        if num_user_messages >= len(self.rubrics[session.topic_id]):
            new_messages = [{"role": "system", "content": init_system_prompt},
                            {"role": "user", "content": "How can I help you?"},
                            *new_messages]

            new_messages[0]["content"] \
                = f"You gathered all necessary information. Say thank you and farewell."
            response = self.llm.generate(new_messages)[0]

            return UserUtterance(
                response,
                True
            )

        new_messages = [{"role": "system", "content": init_system_prompt},
                        {"role": "user", "content": "How can I help you?"},
                        *new_messages]

        best_response = self.conditional_response_generation(new_messages)
        return UserUtterance(
            best_response,
            False
        )


    def conditional_response_generation(self, messages: List[Dict[str, Any]]) -> str:
        self.logger.debug(f"Generate: {json.dumps(messages)}")
        responses = self.llm.generate(messages, **self.gen_kwargs)
        self.logger.debug(f"Response candidates: {responses}")

        best_response = responses[0]
        self.logger.debug(f"Best response: {best_response}")

        return best_response


class OpenAIPlanningBasedUserSimulator(PlanningBasedUserSimulator):
    llm = None

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

    rubric_score_prompt = (
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

    rubric_score_gen_kwargs = {"max_completion_tokens": 1, "n": 1}

    def __init__(self, _id, topics: Dict[str, Topic], rubrics: Dict[str, List[str]], ptkb: List[str]):
        super().__init__(_id, topics, rubrics, ptkb)

        if OpenAIPlanningBasedUserSimulator.llm is None:
            OpenAIPlanningBasedUserSimulator.llm = OpenAIModel(OpenAIModelVersion.GPT_4_1)

        if OpenAIPlanningBasedUserSimulator.st_model is None:
            OpenAIPlanningBasedUserSimulator.st_model = SentenceTransformer("all-mpnet-base-v2")



class OpenAIUnrestrictedUserSimulator(UnrestrictedUserSimulator):
    llm = None

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

    def __init__(self, _id, topics: Dict[str, Topic], rubrics: Dict[str, List[str]], ptkb: List[str]):
        super().__init__(_id, topics, rubrics, ptkb)

        if OpenAIPlanningBasedUserSimulator.llm is None:
            OpenAIPlanningBasedUserSimulator.llm = OpenAIModel(OpenAIModelVersion.GPT_4_1)


