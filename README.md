# TREC iKAT Simulation API

In TREC iKAT Year 3, we offer an interactive task in which a simulated user sends out utterances to participants' systems. For more information on this task please check [the guidelines](https://www.trecikat.com/guidelines/).

This API can be used for two main purposes:
1. [Submitting runs for the interactive task](#submitting-runs). 
2. [Developing, debugging and testing of participants' systems](#debugging--testing-a-system).

The API is available at [https://trec-ikat25.webis.de/simulation/](https://trec-ikat25.webis.de/simulation/). From there you will be redirected to a reference of all provided endpoints and their expected in- and outputs.

## Authentication

Participants need to be registered to TREC iKAT in order to use this API. You can use [this form](https://ir.nist.gov/evalbase/accounts/login/?next=/evalbase/) to do so. As a result, participants will receive a base64-encoded access token. 

All requests to this API have to be authenticated. Participants can authenticate themselves by providing their access token in the HTTP `Authorization` header. 

You can test if your access token is valid by calling the following method:
```bash
curl -H "Authorization: Bearer <token>" https://trec-ikat25.webis.de/simulation/auth/verify
```

If your token is valid, the API will respond with:
```json
{"team_id":  "<TEAM_ID>"}
```

## Submitting Runs

<span style="color: red">**Important:**</span> With the following information the final participant runs will be submitted. For debugging and developing participant systems refer to [this information below](#debugging--testing-a-system).  

Conversations are always user-initiated. In a first step, participants submit meta-information about their run and receive the first user utterance for the first topic. From there, participants and the simulated user take turns in responding to each other's utterances. Users terminate the conversations and switch topics automatically.

### 1. Starting a Run

Participants start a run by providing the following run meta-information and in turn receive the first user utterance for the first topic. 

Please provide the following meta-information:
* `run_id`: Unique name that identifies your run. Please choose a meaningful name (e.g., `teamA-llama3-dense-retrieval`).
* `description`: Brief description of the used approach in this run. 
* `track_persona`: Indicate if your approach extracts and keeps track of persona statements of reoccurring users. 

An example request looks like this:
```bash
curl -X POST -H "Authorization: Bearer <token>" -H "Content-Type: application/json" -d \
 '{
    "run_id": "teamA-llama3-dense-retrieval",
    "description": "The approach uses a retrieval-augmented generation pipeline with llama3.3 70B as generation backbone and a dense retrieval approach for the retrieval of relevant passages.", 
     "track_persona": false
  }' https://trec-ikat25.webis.de/simulation/run/start
```

A response to a successful request looks like this:
```json
{
  "timestamp":"2025-05-06T10:58:33.400920",
  "run_id":"teamA-llama3-dense-retrieval",
  "topic_id":"1-1",
  "user_id":"f3333f5c-8313-4941-beea-f24de25a583a",
  "utterance":"Show me universities with computer science programs.",
  "history":[
    {"role":"user","content":"Show me universities with computer science programs."}
  ],
  "last_response_of_session":false,
  "last_response_of_run":false
}
```
Responses contain the following fields:
* `timestamp`: Time and date of the current response.
* `run_id`: The chosen identifier for the run.
* `topic_id`: Id of the current topic of TREC iKAT 2025 test set. 
* `user_id`: Uuid4 that identifies a (simulated) user the system talks with. This helps to identify reoccurring users. 
* `utterance`: Current utterance of the user.
* `history`: A list of the current and prior utterances in LLM-compatible format that can be used to track the current context of the conversation. 
* `last_response_of_session`: Flag that indicates that the current session (for the current topic) is terminated by the user. If true, the next response will be about a new topic. 
* `last_response_of_run`: Flag that indicates that the current session is terminated by the user and that there are no open topics left. If true, your run is completed and successfully submitted.  

### 2. Responding to User Utterances

After a run is started like shown above, participants receive the first user utterance. From now until the run is completed, participants respond to user utterances by calling the `run/continue` endpoint. Participants should always provide the following information: 
* `run_id`: The chosen identifier for the run.
* `response`: The generated response of the system.
* `citations`: The (up to) top 1000 relevant passages given as their ids and their relevance score. 
* `ptkb_provenance`: (Optional) PTKB statements that are considered relevant for the current turn. 


An example request looks like this:
```bash
curl -X POST -H "Authorization: Bearer <token>" -H "Content-Type: application/json" -d\
 '{
   "run_id": "teamA-llama3-dense-retrieval", 
   "response": "There is University of Amsterdam.",
   "citations": {
     "clueweb22-en0032-04-00208:7": 0.8, 
     "clueweb22-en0027-84-11778:0": 0.4
   },
   "ptkb_provenance": [
     "I live in the Netherlands."
   ]
  }' https://trec-ikat25.webis.de/simulation/run/continue
```

Successful requests always result in responses formatted as mentioned above. 

```json
{
  "timestamp":"2025-05-06T11:16:53.306006","run_name":"teamA-llama3-dense-retrieval",
  "topic_id":"1-1",
  "user_id":"f3333f5c-8313-4941-beea-f24de25a583a",
  "utterance":"That’s a good start, but the initial response wasn’t helpful. Could you specifically tell me which programs at the University of Amsterdam emphasize courses similar to the ones I enjoyed during my bachelor’s degree – specifically data structures, algorithms, data mining, and artificial intelligence?",
  "history":[
    {"role":"user","content":"Show me universities with computer science programs."},
    {"role":"assistant","content":"University of Amsterdam"},
    {"role":"user","content":"That’s a good start, but the initial response wasn’t helpful. Could you specifically tell me which programs at the University of Amsterdam emphasize courses similar to the ones I enjoyed during my bachelor’s degree – specifically data structures, algorithms, data mining, and artificial intelligence?"}],
  "last_response_of_session":false, 
  "last_response_of_run":false
}
```

### 3. Switching Topics

There is no way to manually end the current conversation and move on to the next topic. The (simulated) user is responsible for that decision. This decision is indicated by the flag `last_response_of_session`. If this flag is true, the next call to the `run/continue` endpoint will result in the initial user utterance for the next topic. 

**Important**: If participants provide a response at the turn after this flag becomes true, this response will be ignored. The `response` field can be an empty string or `null` in this case.

### 4. Finishing a Run

When the (simulated) users inquired about all topics in the dataset, the flag `last_response_of_run` will become true. This indicates that the run is done. Further requests after this flag becomes true will lead to errors.

### Limits

Participants can submit up to two runs. Incomplete runs will be evaluated as well. Missing topics will be assessed with a performance of zero.   

## Debugging / Testing a System

Participants can also use the API for debugging and testing their systems. To this end, there are equivalent endpoints that emulate a run submission. 

* `https://trec-ikat25.webis.de/simulation/debug/start`
* `https://trec-ikat25.webis.de/simulation/debug/continue`

These two endpoints expect the exact same inputs as their run submission counterparts. 

**Important:** Responses submitted to the debugging endpoints will not be evaluated. 

### Budget for Requests

Participants are allowed a limited number of requests for the debugging of their systems. The exact number of requests is to be determined. 

To keep track of the available budget, participants can check their available credits with the following request. 

```shell
curl -H "Authorization: Bearer <token>" "https://trec-ikat25.webis.de/simulation/budget/check" 
```



## Monitor Submission Progress

### Check Run Status

Participants can check the status of their runs to make sure that everything worked as expected. The following request can be used to check the status.

```shell
curl -X GET -H "Authorization: Bearer <token>" "https://trec-ikat25.webis.de/simulation/run/status?run_id=teamA-llama3-dense-retrieval"
```

A typical response looks like the following.

```json
{
  "status": "complete",
  "open_topics": [],
  "done_topics": [...]
}
```

Responses contain the following fields:
* `status`: There are three possible values for status:
  * `active`: The requested run is currently being worked on and is not complete yet.
  * `completed`: The requested run is done and was submitted successfully.
  * `inactive`: The run was not completed but (due to an error) the run is currently not active. This can only happen if the server crashes. The run can be worked on as usual which will push the run back into the `active` state.
* `open_topics`: A list of topic ids that still need to be worked on to reach the `complete` status.
* `done_topics`: A list of topic ids of topics that were already completed in this run. 

### Dump Run File

For your own documentation you can get a copy of the run submission file. 

**Important:** You don't have to submit this file anywhere. This file is just for your own reference.

To produce the run file you can run the following command:

```shell
curl -H "Authorization: Bearer <token>" "localhost:8888/run/dump?run_id=teamA-llama3-dense-retrieval"
```

As a response, you will receive the run file in the submission format for this task.

```json
[
  {
    "metadata": {
      "team_id": "teamA",
      "run_id": "teamA-llama3-dense-retrieval",
      "type": "interactive",
      "description": "The approach uses a retrieval-augmented generation pipeline with llama3.3 70B as generation backbone and a dense retrieval approach for the retrieval of relevant passages.",
      "track_persona": 0,
      "topic_id": "1-1_0"
    },
    "responses": [
      {
        "rank": 1,
        "user_utterance": "Okay, let’s start with a list of elite universities in Canada.",
        "text": "I don't know.",
        "citations": {},
        "ptkb_provenance": []
      }
    ],
    "references": {}
  },
  {
     "metadata": {
      "team_id": "teamA",
      "run_id": "teamA-llama3-dense-retrieval",
      "type": "interactive",
      "description": "The approach uses a retrieval-augmented generation pipeline with llama3.3 70B as generation backbone and a dense retrieval approach for the retrieval of relevant passages.",
      "track_persona": 0,
      "topic_id": "1-1_1"
    },
    "responses": [
      {
        "rank": 1,
        "user_utterance": "Specifically, which elite universities exist in Canada that might be suitable for a Computer Science graduate from the Netherlands, considering my preference for moderate climates and lack of a driver's license?",
        "text": "I don't know.",
        "citations": {},
        "ptkb_provenance": []
      }
    ],
    "references": {}
  },
  ...
]
```

## Support

In case of technical issues or other form of feedback, feel free to contact [marcel.gohsen@uni-weimar.de](mailto:marcel.gohsen@uni-weimar.de). 