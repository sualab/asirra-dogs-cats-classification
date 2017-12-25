from abc import abstractmethod
import tensorflow as tf
import numpy as np
import time


class Optimizer(object):
    """
    Base class for gradient-based optimization functions.
    """

    def __init__(self, sess, model, train_set, evaluator, **kwargs):
        """
        Optimizer initializer.
        :param sess: tf.Session.
        :param model: Model to be learned.
        :param train_set: DataSet.
        :param evaluator: Evaluator.
        """
        self.sess = sess
        self.model = model
        self.train_set = train_set
        self.evaluator = evaluator

        self.batch_size = kwargs.pop('batch_size', 256)
        self.num_epochs = kwargs.pop('num_epochs', 320)
        self.init_learning_rate = kwargs.pop('learning_rate', 0.01)

        self.learning_rate_placeholder = tf.placeholder(tf.float32)
        self.optimize = self._optimize_op()
        self.saver = tf.train.Saver()

    def _reset(self):
        """Reset some variables."""
        self.curr_epoch = 1
        self.best_score = self.evaluator.worst_score
        self.curr_learning_rate = self.init_learning_rate    # current learning rate
        self.sess.run(tf.global_variables_initializer())    # initialize all weights

    @abstractmethod
    def _optimize_op(self):
        """
        tf.train.Optimizer.minimize Op for a gradient update.
        This should be implemented, and should not be called manually.
        """
        pass

    def _step(self):
        """
        Make a single gradient update and return its results.
        This should not be called manually.
        """
        step_results = dict()
        # Sample a single batch
        X, y_true = self.train_set.next_batch(self.batch_size, shuffle=True, augment=True)

        # Compute the loss and make update
        _, loss, y_pred = \
            self.sess.run([self.optimize, self.model.loss, self.model.predict],
                          feed_dict={self.model.X: X, self.model.y: y_true,
                                     self.model.is_train: True,
                                     self.learning_rate_placeholder: self.curr_learning_rate})
        step_results['loss'] = loss
        step_results['y_true'] = y_true
        step_results['y_pred'] = y_pred

        return step_results

    def predict(self, dataset, verbose=False):
        """
        Make predictions for the given dataset.
        :param dataset: DataSet.
        :param verbose: Boolean, whether to print details during prediction.
        """
        batch_size = self.batch_size

        pred_results = dict()
        pred_size = dataset.num_examples
        num_steps = pred_size // batch_size

        if verbose:
            print('Running prediction loop...')

        # Evaluation loop
        _y_true, _y_pred = [], []
        start_time = time.time()
        for i in range(num_steps+1):
            if i == num_steps:
                _batch_size = pred_size - num_steps*batch_size
            else:
                _batch_size = batch_size
            X, y_true = dataset.next_batch(_batch_size, shuffle=False, augment=False)

            # Compute predictions
            y_pred = self.sess.run(self.model.predict,
                                   feed_dict={self.model.X: X,
                                              self.model.is_train: False})
            _y_true.append(y_true)
            _y_pred.append(y_pred)
        if verbose:
            print('Total evaluation time(sec): {}'.format(time.time() - start_time))

        _y_true = np.concatenate(_y_true, axis=0)    # (N, 2)
        _y_pred = np.concatenate(_y_pred, axis=0)    # (N, 2)
        pred_results['y_true'] = _y_true
        pred_results['y_pred'] = _y_pred

        return pred_results

    def train(self, eval_set=None, details=False, verbose=True):
        """
        Run optimizer to train the model.
        :param eval_set: Evaluation set, performs evaluation with it on every epoch if it is not None,
                         while performs evaluation on training set instead if it is None.
        :param details: Boolean, whether to return detailed results.
        :param verbose: Boolean, whether to print details during training.
        """
        train_results = dict()    # dictionary to contain training(, evaluation) results and details
        train_size = self.train_set.num_examples
        num_steps_per_epoch = train_size // self.batch_size
        num_steps = self.num_epochs * num_steps_per_epoch

        if verbose:
            print('Running training loop...')
            print('Number of training iterations: {}'.format(num_steps))

        step_losses, step_scores, eval_scores = [], [], []
        start_time = time.time()
        for i in range(num_steps):
            step_results = self._step()
            step_loss = step_results['loss']
            step_losses.append(step_loss)

            if (i+1) % num_steps_per_epoch == 0:
                step_score = self.evaluator.score(step_results['y_true'], step_results['y_pred'])
                step_scores.append(step_score)
                if eval_set is not None:
                    # Evaluate current model
                    eval_results = self.predict(eval_set, verbose=False)
                    eval_score = self.evaluator.score(eval_results['y_true'], eval_results['y_pred'])
                    eval_scores.append(eval_score)

                    if verbose:
                        print('[epoch {}]\tloss: {} |Train performance: {} |Eval performance: {} |learning_rate: {}'\
                              .format(self.curr_epoch, step_loss, step_score, eval_score, self.curr_learning_rate))

                    # Keep track of the current best model for validation set
                    if self.evaluator.is_better(eval_score, self.best_score):
                        self.best_score = eval_score
                        self.saver.save(self.sess, '/tmp/model.ckpt')    # save current weights

                else:
                    if verbose:
                        print('[epoch {}]\tloss: {} |Train performance: {} |learning_rate: {}'\
                              .format(self.curr_epoch, step_loss, step_score, self.curr_learning_rate))

                    # Keep track of the current best model for training set
                    if self.evaluator.is_better(step_score, self.best_score):
                        self.best_score = step_score
                        self.saver.save(self.sess, '/tmp/model.ckpt')    # save current weights

                self.curr_epoch += 1

        if verbose:
            print('Total training time(sec): {}'.format(time.time() - start_time))
            print('Best {} score: {}'.format('evaluation' if eval else 'training',
                                             self.best_score))

        if details:
            # Store training results in a dictionary
            train_results['step_losses'] = step_losses    # (num_iterations)
            train_results['step_scores'] = step_scores    # (num_epochs)
            if eval_set is not None:
                train_results['eval_scores'] = eval_scores    # (num_epochs)

            return details

        print('Done.')
