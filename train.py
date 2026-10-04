"""Container entrypoint. Kubernetes runs ``python3 train.py``."""

from fda_classifier.train import main

if __name__ == "__main__":
    main()
