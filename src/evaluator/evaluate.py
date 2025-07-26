import asyncio
import json
import os
from datetime import datetime
from typing import Dict, List

from dotenv import load_dotenv
from langfuse import get_client
from langfuse.model import DatasetItem, DatasetStatus

from code_context_provider.servers.context.agent import CodeSnippetFinder
from code_context_provider.evaluator.agent import CodeAgentTypeParser, CodeSnippetResult
from code_context_provider.evaluator.judge import LLMJudge
from code_context_provider.evaluator.config import JudgeConfig

load_dotenv()

config = JudgeConfig()
langfuse = get_client()
RUN_METADATA = {
    "Agent Model": config.code_snippet_finder_model_name,
    "Judge Model": config.llm_judge_model_name,
}


async def process_item(
    worker_id: int,
    item: DatasetItem,
    agent: CodeSnippetFinder,
    experiment_name: str,
    work_queue: asyncio.Queue,
    results_queue: asyncio.Queue,
    log_path: str,
    file_lock: asyncio.Lock,
) -> None:
    try:
        with item.run(run_name=experiment_name, run_metadata=RUN_METADATA) as root_span:
            question = item.input["question"]
            print(f"Worker {worker_id} started processing: {question}")

            with langfuse.start_as_current_generation(
                name="agentic-search",
                input=question,
            ) as generation:
                actual_result_plain_text = await agent.run(question)
                code_snippet_result: CodeSnippetResult = await CodeAgentTypeParser().run(actual_result_plain_text)

                generation.update(output=code_snippet_result.model_dump_json())

            with langfuse.start_as_current_generation(
                name="llm-judge",
                input=code_snippet_result.model_dump_json(),
            ) as generation:
                llm_judge = LLMJudge()
                evaluation_result = await llm_judge.run(
                    question=question,
                    expected_answer=CodeSnippetResult(
                        code=item.expected_output["snippet"],
                        language=item.expected_output["language"],
                        description=item.expected_output["description"],
                    ),
                    actual_answer=code_snippet_result,
                )
                generation.update(output=evaluation_result.model_dump_json())

            print(f"Finished processing: {question}")
            langfuse.update_current_trace(
                input=code_snippet_result.model_dump_json(),
                output=evaluation_result.model_dump_json(),
            )
            root_span.score_trace(name="score", value=1 if evaluation_result.is_pass else 0)

            async with file_lock:
                try:
                    if os.path.exists(log_path):
                        with open(log_path, "r") as f:
                            evaluation_log = json.load(f)
                    else:
                        evaluation_log = []
                except Exception as e:
                    print(f"Error reading log file: {e}")
                    evaluation_log = []
                evaluation_log.append({"question": question, "result": evaluation_result.model_dump()})
                with open(log_path, "w") as f:
                    json.dump(evaluation_log, f, indent=2)

            await results_queue.put((question, evaluation_result))

    except Exception as e:
        print(f"Worker {worker_id} error: {e}")
        await results_queue.put(e)
    finally:
        work_queue.task_done()


async def run_experiment(experiment_name: str) -> float:
    try:
        dataset = langfuse.get_dataset(config.langfuse_dataset_name)
        active_items = [i for i in dataset.items if i.status == DatasetStatus.ACTIVE]

        total_score = 0.0
        total_pass = 0.0
        evaluation_log: List[Dict] = []

        work_queue = asyncio.Queue()
        results_queue = asyncio.Queue()

        for item in active_items:
            await work_queue.put(item)

        os.makedirs("logs", exist_ok=True)
        log_path = f"logs/evaluation-{experiment_name}.json"
        file_lock = asyncio.Lock()

        async def worker(worker_id: int):
            async with CodeSnippetFinder() as agent:
                while True:
                    try:
                        item = await asyncio.wait_for(work_queue.get(), timeout=1.0)
                    except asyncio.TimeoutError:
                        break  # queue is empty

                    await process_item(
                        worker_id,
                        item,
                        agent,
                        experiment_name,
                        work_queue,
                        results_queue,
                        log_path,
                        file_lock,
                    )

        number_of_workers: int = 5  # for parallel item evaluation
        workers = [asyncio.create_task(worker(i)) for i in range(number_of_workers)]

        await work_queue.join()

        for w in workers:
            w.cancel()

        while not results_queue.empty():
            result = await results_queue.get()
            if isinstance(result, Exception):
                print(f"Item failed: {result!r}")
            else:
                question, ev = result
                total_pass += 1 if ev.is_pass else 0
                evaluation_log.append({"question": question, "result": ev.model_dump()})

        avg_score = total_score / max(len(evaluation_log), 1)
        print(f"Total Evaluate/Available: {len(evaluation_log)}/{len(active_items)}")
        print(f"Overall metrics for {experiment_name}:")
        print(f"Average Score: {avg_score:.4f}")
        print(f"Fail/Pass Score: {total_pass / len(evaluation_log):.4f}")

        return avg_score

    finally:
        langfuse.flush()


def main():
    """Main entry point for the evaluation script."""
    timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M")
    asyncio.run(run_experiment(f"codesnippet-evaluation-{timestamp}"))


if __name__ == "__main__":
    main()
