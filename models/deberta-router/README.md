---
tags:
- setfit
- sentence-transformers
- text-classification
- generated_from_setfit_trainer
widget:
- text: Use the calculator tool to find the exact tip amount, then email it to john
- text: Hello there!
- text: Plan a 3-day itinerary for Tokyo and book the flights using the travel API
- text: How do I setup a docker-compose for postgres and node?
- text: Count the number of words in this paragraph
metrics:
- accuracy
pipeline_tag: text-classification
library_name: setfit
inference: true
base_model: microsoft/deberta-v3-small
model-index:
- name: SetFit with microsoft/deberta-v3-small
  results:
  - task:
      type: text-classification
      name: Text Classification
    dataset:
      name: Unknown
      type: unknown
      split: test
    metrics:
    - type: accuracy
      value: 0.7857142857142857
      name: Accuracy
---

# SetFit with microsoft/deberta-v3-small

This is a [SetFit](https://github.com/huggingface/setfit) model that can be used for Text Classification. This SetFit model uses [microsoft/deberta-v3-small](https://huggingface.co/microsoft/deberta-v3-small) as the Sentence Transformer embedding model. A [LogisticRegression](https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.LogisticRegression.html) instance is used for classification.

The model has been trained using an efficient few-shot learning technique that involves:

1. Fine-tuning a [Sentence Transformer](https://www.sbert.net) with contrastive learning.
2. Training a classification head with features from the fine-tuned Sentence Transformer.

## Model Details

### Model Description
- **Model Type:** SetFit
- **Sentence Transformer body:** [microsoft/deberta-v3-small](https://huggingface.co/microsoft/deberta-v3-small)
- **Classification head:** a [LogisticRegression](https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.LogisticRegression.html) instance
- **Maximum Sequence Length:** 512 tokens
- **Number of Classes:** 7 classes
<!-- - **Training Dataset:** [Unknown](https://huggingface.co/datasets/unknown) -->
<!-- - **Language:** Unknown -->
<!-- - **License:** Unknown -->

### Model Sources

- **Repository:** [SetFit on GitHub](https://github.com/huggingface/setfit)
- **Paper:** [Efficient Few-Shot Learning Without Prompts](https://arxiv.org/abs/2209.11055)
- **Blogpost:** [SetFit: Efficient Few-Shot Learning Without Prompts](https://huggingface.co/blog/setfit)

### Model Labels
| Label      | Examples                                                                                                                                                                                                                                                                   |
|:-----------|:---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| UTILITY    | <ul><li>'Sort this alphabetical list: zebra, apple, mango'</li><li>'What is the square root of 144?'</li><li>'Calculate 455 * 89 / 3'</li></ul>                                                                                                                            |
| EXTRACTION | <ul><li>'Identify all the dates mentioned in the article'</li><li>'Pull out the names and phone numbers from this document'</li><li>'Extract the total invoice amount and due date from this email'</li></ul>                                                              |
| CODE       | <ul><li>'Help me optimize this SQL query for better performance'</li><li>"Can you debug this react component? It's throwing a null pointer"</li><li>'What is the difference between a class and an interface?'</li></ul>                                                   |
| CHAT       | <ul><li>'Tell me a joke'</li><li>'Can we just talk for a bit?'</li><li>"That's hilarious!"</li></ul>                                                                                                                                                                       |
| AGENTS     | <ul><li>'Use your terminal to find all files larger than 1GB and list them'</li><li>"Check the weather in London and if it's raining, send a slack message to the team"</li><li>'I need you to browse the web, find the top 5 news articles, and summarize them'</li></ul> |
| CREATIVE   | <ul><li>'Draft a compelling intro for my fantasy novel'</li><li>'Write a haiku about programming'</li><li>'Compose a poem about the autumn leaves'</li></ul>                                                                                                               |
| ANALYSIS   | <ul><li>'Summarize the main arguments of the paper on quantum computing'</li><li>'Evaluate the performance metrics of these two machine learning models'</li><li>'Explain the statistical significance of a p-value less than 0.05'</li></ul>                              |

## Evaluation

### Metrics
| Label   | Accuracy |
|:--------|:---------|
| **all** | 0.7857   |

## Uses

### Direct Use for Inference

First install the SetFit library:

```bash
pip install setfit
```

Then you can load this model and run inference.

```python
from setfit import SetFitModel

# Download from the 🤗 Hub
model = SetFitModel.from_pretrained("setfit_model_id")
# Run inference
preds = model("Hello there!")
```

<!--
### Downstream Use

*List how someone could finetune this model on their own dataset.*
-->

<!--
### Out-of-Scope Use

*List how the model may foreseeably be misused and address what users ought not to do with the model.*
-->

<!--
## Bias, Risks and Limitations

*What are the known or foreseeable issues stemming from this model? You could also flag here known failure cases or weaknesses of the model.*
-->

<!--
### Recommendations

*What are recommendations with respect to the foreseeable issues? For example, filtering explicit content.*
-->

## Training Details

### Training Set Metrics
| Training set | Min | Median | Max |
|:-------------|:----|:-------|:----|
| Word count   | 2   | 8.5536 | 16  |

| Label      | Training Sample Count |
|:-----------|:----------------------|
| CODE       | 8                     |
| ANALYSIS   | 8                     |
| CHAT       | 8                     |
| CREATIVE   | 8                     |
| EXTRACTION | 9                     |
| UTILITY    | 9                     |
| AGENTS     | 6                     |

### Training Hyperparameters
- batch_size: (16, 16)
- num_epochs: (3, 3)
- max_steps: -1
- sampling_strategy: oversampling
- body_learning_rate: (2e-05, 1e-05)
- head_learning_rate: 0.01
- loss: CosineSimilarityLoss
- distance_metric: cosine_distance
- margin: 0.25
- end_to_end: False
- use_amp: False
- warmup_proportion: 0.1
- l2_weight: 0.01
- seed: 42
- run_name: ai-router-deberta
- evaluation_strategy: epoch
- eval_max_steps: -1
- load_best_model_at_end: True

### Training Results
| Epoch  | Step | Training Loss | Validation Loss |
|:------:|:----:|:-------------:|:---------------:|
| 0.0060 | 1    | 0.1958        | -               |
| 0.2976 | 50   | 0.2616        | -               |
| 0.5952 | 100  | 0.0868        | -               |
| 0.8929 | 150  | 0.0324        | -               |
| 1.0    | 168  | -             | 0.0646          |
| 1.1905 | 200  | 0.0071        | -               |
| 1.4881 | 250  | 0.0039        | -               |
| 1.7857 | 300  | 0.0028        | -               |
| 2.0    | 336  | -             | 0.0570          |
| 2.0833 | 350  | 0.0025        | -               |
| 2.3810 | 400  | 0.002         | -               |
| 2.6786 | 450  | 0.0018        | -               |
| 2.9762 | 500  | 0.0019        | -               |
| 3.0    | 504  | -             | 0.0546          |

### Framework Versions
- Python: 3.12.13
- SetFit: 1.1.3
- Sentence Transformers: 3.4.1
- Transformers: 4.57.6
- PyTorch: 2.10.0+cu128
- Datasets: 4.8.4
- Tokenizers: 0.22.2

## Citation

### BibTeX
```bibtex
@article{https://doi.org/10.48550/arxiv.2209.11055,
    doi = {10.48550/ARXIV.2209.11055},
    url = {https://arxiv.org/abs/2209.11055},
    author = {Tunstall, Lewis and Reimers, Nils and Jo, Unso Eun Seo and Bates, Luke and Korat, Daniel and Wasserblat, Moshe and Pereg, Oren},
    keywords = {Computation and Language (cs.CL), FOS: Computer and information sciences, FOS: Computer and information sciences},
    title = {Efficient Few-Shot Learning Without Prompts},
    publisher = {arXiv},
    year = {2022},
    copyright = {Creative Commons Attribution 4.0 International}
}
```

<!--
## Glossary

*Clearly define terms in order to be accessible across audiences.*
-->

<!--
## Model Card Authors

*Lists the people who create the model card, providing recognition and accountability for the detailed work that goes into its construction.*
-->

<!--
## Model Card Contact

*Provides a way for people who have updates to the Model Card, suggestions, or questions, to contact the Model Card authors.*
-->