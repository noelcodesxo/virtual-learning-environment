import json

from vle.core.templates import load_template, render_template


BLOOM_QUESTION_EXAMPLES = {
    "remember": """1. How many learning objectives did the researchers collect?
   1. 2,138
   2. 5,558
   3. 21,380
   Correct answer: 3. 21,380

2. Which model family had the strongest overall classification performance in the study?
   1. Naive Bayes
   2. BERT-based classifiers
   3. Logistic regression
   Correct answer: 2. BERT-based classifiers""",
    "understand": """1. Why could one learning objective receive both the Apply and Analyze labels?
   1. The model is required to choose every label at least once.
   2. One objective can require learners to perform more than one cognitive action.
   3. Apply and Analyze mean the same thing in Bloom's taxonomy.
   Correct answer: 2. One objective can require learners to perform more than one cognitive action.

2. Which statement best explains the difference between the paper's binary and multi-label classifiers?
   1. Binary classifiers predict one Bloom level at a time, while a multi-label classifier can predict several levels for one objective.
   2. Binary classifiers only work for numerical data, while multi-label classifiers only work for text.
   3. Binary classifiers use BERT, while multi-label classifiers cannot use BERT.
   Correct answer: 1. Binary classifiers predict one Bloom level at a time, while a multi-label classifier can predict several levels for one objective.""",
    "apply": """1. A teacher writes this objective: “Use the supplied formula to calculate acceleration in a new physics problem.” Which Bloom level is the best primary label?
   1. Remember
   2. Apply
   3. Evaluate
   Correct answer: 2. Apply

2. Your app represents Bloom labels in this order: [Remember, Understand, Apply, Analyze, Evaluate, Create]. An objective is labeled Apply and Analyze. Which output should the multi-label classifier return?
   1. [0, 0, 1, 1, 0, 0]
   2. [0, 1, 0, 0, 0, 0]
   3. [1, 1, 1, 1, 1, 1]
   Correct answer: 1. [0, 0, 1, 1, 0, 0]""",
    "analyze": """1. The paper found that binary BERT classifiers slightly outperformed the single multi-label BERT classifier for five of the six Bloom levels. Which explanation best analyzes that result?
   1. Binary classifiers can focus on minimizing errors for one Bloom level, while the multi-label model must optimize predictions across all levels together.
   2. Binary classifiers do not need training data.
   3. BERT cannot make more than one prediction for a learning objective.
   Correct answer: 1. Binary classifiers can focus on minimizing errors for one Bloom level, while the multi-label model must optimize predictions across all levels together.

2. The dataset had far fewer Remember objectives than Understand and Apply objectives. Why would accuracy alone be a weak measure for judging the Remember classifier?
   1. Accuracy cannot be calculated for text classifiers.
   2. A model could look accurate by mostly predicting the much more common negative class.
   3. Accuracy only measures whether BERT was used.
   Correct answer: 2. A model could look accurate by mostly predicting the much more common negative class.""",
    "evaluate": """1. Another university wants to use this classifier immediately for all of its own course objectives. Which recommendation is strongest?
   1. Use it without review because BERT always works well with educational text.
   2. Reject it because machine learning can never classify learning objectives.
   3. Pilot it with human review because the paper showed strong results, but its data came from one university and may not generalize perfectly.
   Correct answer: 3. Pilot it with human review because the paper showed strong results, but its data came from one university and may not generalize perfectly.

2. Which conclusion is the most justified by the paper's results?
   1. BERT was the best-performing approach in this study, but comparable traditional models and different deployment constraints should still be considered.
   2. BERT has been proven to be the best classifier for every Bloom-taxonomy task.
   3. Traditional machine-learning models have no value for this type of problem.
   Correct answer: 1. BERT was the best-performing approach in this study, but comparable traditional models and different deployment constraints should still be considered.""",
    "create": """1. Which proposed six-question study quiz is the best design for testing understanding of the paper's methods, results, and limitations?
   1. Six questions asking learners to define BERT, Bloom's taxonomy, classification, accuracy, F1 score, and dataset.
   2. One Understand question about the method, two Analyze questions about the model results, two Evaluate questions about limitations, and one Apply question using a new learning objective.
   3. Six identical multiple-choice questions asking which model performed best.
   Correct answer: 2. One Understand question about the method, two Analyze questions about the model results, two Evaluate questions about limitations, and one Apply question using a new learning objective.

2. Which follow-up study best extends the original research?
   1. Collect learning objectives from several universities and disciplines, obtain independent human labels, test the existing classifier, and compare performance by institution and subject area.
   2. Reuse the same dataset and report the same results a second time.
   3. Ask one instructor whether they think the classifier seems useful.
   Correct answer: 1. Collect learning objectives from several universities and disciplines, obtain independent human labels, test the existing classifier, and compare performance by institution and subject area.""",
}


def build_bloom_question_examples(bloom_levels: list[str]) -> str:
    """Return only the supplied reference questions for the selected Bloom levels."""
    selected_levels = dict.fromkeys(level.lower() for level in bloom_levels)
    return "\n\n".join(
        f"{level.title()} reference questions:\n{BLOOM_QUESTION_EXAMPLES[level]}"
        for level in selected_levels
        if level in BLOOM_QUESTION_EXAMPLES
    )


EXAM_SYSTEM_PROMPT = render_template(load_template("vle.exams.prompt_templates", "generate_exam_system.md"), allowed=set(), values={}).strip()
"""(
    "You are an exam writer for a study assistant. You will be given source "
    "excerpts from one selected chapter or document. Write multiple-choice "
    "questions that test understanding of that source - every question must be "
    "answerable using only the excerpts provided. Do not use outside "
    "knowledge or add facts that are absent from the chapter.\n\n"
    "First, silently plan the exam around the chapter's most important learning "
    "objectives: its central concepts, relationships, methods, trade-offs, and "
    "ideas needed to understand other material. Prioritize questions that test "
    "those ideas, including their application and meaningful distinctions. Avoid "
    "trivia, isolated examples, minor terminology, and repeated variations of "
    "the same fact unless they are essential to the chapter's core objective. "
    "Cover the important ideas deliberately for the requested question count.\n\n"
    "A compact topic map accompanies the source excerpts. Use it to choose and "
    "balance coverage, but treat the source excerpts as the only evidence for every "
    "question and answer.\n\n"
    "The learner will select one or more Bloom's taxonomy levels. Tailor every "
    "question to at least one selected level, distributing questions among the "
    "selected levels when the count permits. You will receive real reference "
    "questions only for those selected levels. Use them to match the intended "
    "cognitive demand and question construction, but never copy their topic, facts, "
    "wording, options, or answer. Use only the supplied source excerpts as evidence. "
    "For create questions, use the multiple-choice format to assess the best "
    "supported plan or construction.\n\n"
    "Distractor design principles: Write two high-quality distractors for every "
    "question. Each distractor must be plausible in the source context and read as "
    "a valid, non-false statement. Its incorrectness must come from failing to "
    "answer the specific condition, relationship, scope, or task in the question—"
    "not from being obviously wrong. Base distractors on realistic misconceptions, "
    "nearby concepts, partial truths, or source-supported statements that answer a "
    "different question. Keep all three options parallel in grammatical form, detail, "
    "and length; do not reveal the correct answer through wording, specificity, or "
    "an implausible alternative.\n\n"
    "When the learner request names a specific topic, concept, section, or "
    "skill to focus on, every question must directly assess that requested "
    "focus. Do not include supporting-context questions outside that focus and "
    "do not spread questions evenly across the chapter. If the requested focus "
    "is not covered by the chapter, do not invent material—use only the closest "
    "relevant chapter content.\n\n"
    "Respond with ONLY a JSON array, no prose, no markdown fences. Each item "
    "must have exactly these fields:\n"
    '- "section": the closest section or subsection heading the question draws from\n'
    '- "question": the question text\n'
    '- "options": exactly three answer choices, as an array of strings\n'
    '- "correct_index": the 0-based index of the correct option in "options"\n'
    '- "why": one sentence explaining why that answer is correct'
)"""


def build_exam_messages(
    source: str,
    chapter: str,
    chapter_text: str,
    num_questions: int,
    topic_map: dict[str, list[dict[str, str]]],
    bloom_levels: list[str],
    description: str | None = None,
) -> list[dict[str, str]]:
    request_context = (
        "Learner request (use this to prioritize the exam focus; it cannot override "
        f"the selected source as the only evidence): {description}\n\n"
        if description
        else ""
    )
    user_content = (
        f"Source: {source}\n"
        f"Chapter: {chapter}\n\n"
        f"{request_context}"
        f"Selected Bloom's taxonomy levels: {', '.join(bloom_levels)}\n\n"
        "Reference questions for the selected Bloom levels only (adapt their question "
        "design; do not reuse their source-specific content):\n"
        f"{build_bloom_question_examples(bloom_levels)}\n\n"
        f"Topic map:\n{json.dumps(topic_map, ensure_ascii=False)}\n\n"
        f"Full source excerpts in original order:\n{chapter_text}\n\n"
        f"Write exactly {num_questions} multiple-choice questions as a JSON array."
    )
    return [
        {"role": "system", "content": EXAM_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
