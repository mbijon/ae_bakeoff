import os

import pytorch_lightning as pl

import building
import downstream
import run
from utils import ResultsMixin


class ReproductionRun:
    def __init__(self):
        self.checkpoints = Checkpoints()
        self.classification_results = ClassificationDownstream()
        self.anomaly_detection_results = AnomalyDownstream()
        self.latent_results = LatentDownstream()

    def reproduce(self):
        if self.checkpoints.empty():
            self.train_all()
            self.checkpoints.save()
        for model_type in self.checkpoints.keys():
            self.perform_downstream(model_type)

    def train_all(self):
        for model_type in run.AUTOENCODERS:
            self.checkpoints[model_type] = {}
            self.checkpoints[model_type]['general'] = run.run(model_type)
            self.checkpoints[model_type]['anomaly'] = run.run(model_type, anomaly=True)

    def _get_log_path(self):
        script_path = os.path.dirname(__file__)
        log_path = os.path.join(script_path, '..', 'logs')
        log_path = os.path.normpath(log_path)

        return log_path

    def perform_downstream(self, model_type):
        self.perform_classification(model_type)
        self.perform_anomaly_detection(model_type)

    def perform_classification(self, model_type):
        pl.seed_everything(42)
        checkpoint_path = self.checkpoints[model_type]['general']
        test_results = self._get_test_accuracy(model_type, checkpoint_path)
        self.classification_results[model_type] = test_results['test/accuracy']
        self.classification_results.save()

    def _get_test_accuracy(self, model_type, checkpoint_path):
        data = building.build_datamodule('classification')
        classifier = downstream.Classifier.from_autoencoder_checkpoint(model_type, data, checkpoint_path)
        trainer = self._get_classification_trainer()

        trainer.fit(classifier, datamodule=data)
        test_results, *_ = trainer.test(datamodule=data)

        return test_results

    def _get_classification_trainer(self):
        checkpoint_callback = pl.callbacks.ModelCheckpoint('val/accuracy', mode='max')
        early_stop_callback = pl.callbacks.EarlyStopping('val/accuracy', mode='max')
        trainer = pl.Trainer(logger=False,
                             max_epochs=20,
                             checkpoint_callback=checkpoint_callback,
                             early_stop_callback=early_stop_callback)

        return trainer

    def perform_anomaly_detection(self, model_type):
        pl.seed_everything(42)
        checkpoint_path = self.checkpoints[model_type]['general']
        fpr, tpr, thresholds, auc = self._get_test_roc(model_type, checkpoint_path)
        self.anomaly_detection_results[model_type] = {'fpr': fpr.tolist(),
                                                      'tpr': tpr.tolist(),
                                                      'thresholds': thresholds.tolist(),
                                                      'auc': auc}
        self.anomaly_detection_results.save()

    def _get_test_roc(self, model_type, checkpoint_path):
        data = building.build_datamodule(anomaly=True)
        anomaly_detector = downstream.AnomalyDetection.from_autoencoder_checkpoint(model_type, data, checkpoint_path)
        fpr, tpr, thresholds, auc = anomaly_detector.get_test_roc(data)

        return fpr, tpr, thresholds, auc


class Checkpoints(ResultsMixin):
    def _get_results_path(self):
        log_path = self._get_log_path()
        checkpoint_path = os.path.join(log_path, 'checkpoints.json')

        return checkpoint_path


class ClassificationDownstream(ResultsMixin):
    def _get_results_path(self):
        log_path = self._get_log_path()
        results_path = os.path.join(log_path, 'classification_results.json')

        return results_path


class AnomalyDownstream(ResultsMixin):
    def _get_results_path(self):
        log_path = self._get_log_path()
        results_path = os.path.join(log_path, 'anomaly_results.json')

        return results_path


class LatentDownstream(ResultsMixin):
    def _get_results_path(self):
        log_path = self._get_log_path()
        results_path = os.path.join(log_path, 'latent_results.json')

        return results_path


if __name__ == '__main__':
    ReproductionRun().reproduce()
