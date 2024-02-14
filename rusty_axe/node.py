import numpy as np
from copy import copy, deepcopy

# RELINT THIS

class Node:

    def __init__(self, node_json, tree, forest, parent=None, cache=False, lr=None, level=0):


        """
        Here we initialize the node from a json object generated by random forest

        Note the unpacking is recursive to maintain the tree structure
        There are probably other ways to encode this like network connectivity
        matrices but I think this leads to slightly more elegant structure.
        We got python, we might as well use it

        """

        self.cache = cache

        self.tree = tree
        self.forest = forest
        self.parent = parent
        self.lr = lr
        self.level = level
        self.filter = Filter(node_json['filter'], self)
        self.local_samples = None
        if 'means' in node_json:
            if node_json['means'] is not None:
                self.mean_cache = np.array(node_json['means'])
        if 'medians' in node_json:
            if node_json['medians'] is not None:
                self.median_cache = np.array(node_json['medians'])
        self.weights = np.ones(len(self.forest.output_features))
        self.children = []
        self.child_clusters = ([], [])

        # Recursion starts here for maintaining hierarchy

        if len(node_json['children']) > 0:
            self.children.append(Node(
                node_json['children'][0], self.tree, self.forest, parent=self, lr=0, level=level + 1, cache=cache))
            self.children.append(Node(
                node_json['children'][1], self.tree, self.forest, parent=self, lr=1, level=level + 1, cache=cache))
        else:
            self.local_samples = node_json['samples']
            # pass

    # Two nodes used for testing, not relevant for normal operation

    def null():

        null_dictionary = {}
        null_dictionary['feature'] = None
        null_dictionary['split'] = None
        null_dictionary['features'] = []
        null_dictionary['samples'] = []
        null_dictionary['children'] = []
        return Node(null_dictionary,None,None)

    def test_node(feature,split,features,samples,medians,dispersions):
        test_node = Node.null()
        test_node.feature = feature
        test_node.split = split
        test_node.features.extend(features)
        test_node.samples.extend(samples)
        return test_node

    def samples(self):
        if self.local_samples is None:
            leaves = self.leaves()
            samples = [s for l in leaves for s in l.local_samples]
            return samples
        else:
            return self.local_samples

    def pop(self):
        if hasattr(self, 'pop_cache'):
            return self.pop_cache
        else:
            pop = len(self.samples())
            self.pop_cache = pop
            return self.pop_cache

    def nodes(self):

        # Obtains all descendant nodes in deterministic order
        # Left to right

        nodes = []
        for child in self.children:
            nodes.extend(child.nodes())
        for child in self.children:
            nodes.append(child)
        return nodes

    def encoding(self):
        if self.cache:
            if hasattr(self, 'encoding_cache'):
                return self.encoding_cache
        encoding = np.zeros(len(self.forest.samples), dtype=bool)
        encoding[self.samples()] = True
        if self.cache:
            self.encoding_cache = encoding
        return encoding

    def sample_mask(self):
        # Alias of encoding
        return self.encoding()

    def node_counts(self):

        # Obtains the count matrix of samples belonging to this node
        # Samples are in order they are in the node

        copy = self.forest.output[self.encoding()].copy()
        return copy

    def compute_cache(self):

        for child in self.children:
            child.compute_cache()

        self.cache = True

        counts = self.node_counts()
        means = np.mean(counts, axis=0)
        medians = np.median(counts, axis=0)
        srs = np.sum(np.power(counts - means, 2), axis=0)

        self.mean_cache = means
        self.median_cache = medians
        self.srs_cache = srs

        for child in self.children:
            additive_mean = child.means() - means
            child.additive_mean_cache = additive_mean

    def medians(self):

        # Medians of all features in this node. Relies on node_counts

        if self.cache:
            if hasattr(self, 'median_cache'):
                return self.median_cache
        matrix = self.node_counts()
        medians = np.median(matrix, axis=0)
        if self.cache:
            self.median_cache = medians
        return medians

    def means(self):

        # Means of all features within this node. Relies on node_counts

        if self.cache:
            if hasattr(self, 'mean_cache'):
                return self.mean_cache
        matrix = self.node_counts()
        means = np.mean(matrix, axis=0)
        if self.cache:
            self.mean_cache = means
        return means

    def feature_median(self, feature):

        # Median of a specific feature within this node.
        # Much faster than getting the entire matrix, obviously, unless medians are cached

        fi = self.forest.truth_dictionary.feature_dictionary[feature]
        values = self.forest.output[self.sample_mask()].T[fi]
        return np.median(values)

    def sample_cluster_means(self):

        labels = self.forest.sample_labels[self.samples()]
        one_hot = np.array(
            [labels == x.id for x in self.forest.sample_clusters])
        means = np.mean(one_hot, axis=0)
        return means

    def feature_mean(self, feature):

        # As above, mean of an individual feature within this node

        fi = self.forest.truth_dictionary.feature_dictionary[feature]

        if hasattr(self, 'mean_cache'):
            return self.mean_cache[fi]
        else:
            values = self.forest.output[self.sample_mask()].T[fi]
            return np.mean(values)

    def feature_partial(self, feature):
        if len(self.children) > 1:

            descendants = self.nodes()
            if self.sister() is not None:
                descendants.extend(self.sister().nodes())

            additives = [n.feature_additive_mean(feature) for n in descendants]
            populations = [n.pop() for n in descendants]

            self_additive = self.feature_additive_mean(feature)
            self_ads = np.power(self_additive, 2) * self.pop()
            adrs = np.dot(np.power(additives, 2).T, populations)

            adrf = self_ads / (self_ads + adrs)

            if not np.isfinite(adrf):
                adrf = 0

            partial = np.sign(self_additive) * adrf

            return partial
        else:
            return self.feature_additive_mean(feature)

    def mean_residuals(self):

        counts = self.node_counts()
        means = self.means()
        residuals = counts - means

        return residuals

    def median_residuals(self):

        counts = self.node_counts()
        medians = self.medians()
        residuals = counts - medians

        return residuals

    def explained(self):
        if self.parent is None:
            if hasattr(self, 'explained_cache'):
                return self.explained_cache
            else:
                additives = self.forest.node_representation(
                    self.nodes(), mode='additive_mean')
                squared = np.power(additives, 2)
                return np.sum(squared, axis=0)
        else:
            return self.root().explained()

    def absolute_partials(self):
        if self.parent is not None:
            explained = self.explained()
            own_additive = self.additive_mean_gains()
            own = np.power(own_additive, 2)
            signed = np.sign(own_additive) * (own / explained)
            return signed
        else:
            return np.zeros(len(self.forest.output_features))

    def partials(self):

        # Partial gain, which is the signed percentage of all variance explained by the tree. Useful for scaling the variance explained by a given node for each feature to the total information explained, allowing comparisons of explained variance in all features.

        if len(self.children) > 1:

            descendants = self.nodes()
            if self.sister() is not None:
                descendants.extend(self.sister().nodes())

            additives = self.forest.node_representation(
                descendants, mode='additive_mean')
            populations = np.sum(self.forest.node_representation(
                descendants, mode='sample'), axis=1)

            self_additives = self.additive_mean_gains()
            self_ads = np.power(self_additives, 2) * self.pop()
            adrs = np.dot(np.power(additives, 2).T, populations)

            adrf = self_ads / (self_ads + adrs)

            adrf[~np.isfinite(adrf)] = 0

            partials = np.sign(self_additives) * adrf

            return partials
        else:
            return self.additive_mean_gains()

    def mean_residual_doublet(self):

        # Residuals of samples in this node as they appear in this node  and in the parent. Residuals in the parent are relative to the parent mean. This is a quantity that can be used without normalization for error calculations but it's probably not useful externally.

        counts = self.node_counts()
        self_means = self.means()
        if self.parent is not None:
            parent_means = self.parent.means()
        else:
            parent_means = np.zeros(len(self_means.shape))

        self_residuals = counts - self_means
        parent_residuals = counts - parent_means

        return self_residuals, parent_residuals

    def squared_residual_sum(self):
        if hasattr(self, 'srs_cache'):
            return self.srs_cache
        else:
            squared_residuals = np.power(self.mean_residuals(), 2)
            srs = np.sum(squared_residuals, axis=0)
            if self.cache:
                self.srs_cache = srs
            return srs

    def squared_residual_doublet(self):

        # Sum of squared residuals for samples of this node in this node and the parent.
        # Can be cached more compactly than the mean residual doublet and useful for COV calculations.

        self_residuals, parent_residuals = self.mean_residual_doublet()
        self_srs = np.sum(np.power(self_residuals, 2), axis=0)
        parent_srs = np.sum(np.power(parent_residuals, 2), axis=0)

        return self_srs, parent_srs

    def coefficient_of_determination(self):
        self_srs = self.squared_residual_sum()
        if self.parent is not None:
            parent_srs = self.parent.squared_residual_sum()
            cod = 1 - (np.sum(self_srs) / self.pop()) / \
                (np.sum(parent_srs) / self.parent.pop())
        else:
            cod = np.zeros(self.pop)

        return cod

    def dispersions(self, mode='mean'):

        # Dispersions of this node. currently hardcoded for L2 norm relative
        # to central tendency

        if self.cache:
            if hasattr(self, 'dispersion_cache'):
                return self.dispersion_cache

        if mode == 'mean':
            residuals = self.mean_residuals()
        elif mode == 'median':
            residuals = self.median_residuals()
        else:
            raise Exception(f"Mode not recognized:{mode}")
        dispersions = np.mean(np.power(residuals, 2),axis=0)
        if self.cache:
            self.dispersion_cache = dispersions
        return dispersions

    def mean_error_ratio(self):

        # Can't call to parent residuals because parent will have other samples not
        # present in this node

        counts = self.node_counts()
        self_predictions = self.means()
        if self.parent is not None:
            parent_predictions = self.parent.means()
        else:
            parent_predictions = self.means()
        self_error = np.sum(np.power(counts - self_predictions, 2), axis=0) + 1
        parent_error = np.sum(
            np.power(counts - parent_predictions, 2), axis=0) + 1

        return self_error / parent_error

    def absolute_gains(self):

        # Gains in dispersion relative to the root of the tree this node belongs to.
        # Only works if dispersions are of the summation type (eg sum of squared errors etc)

        if self.cache:
            if hasattr(self, 'absolute_gain_cache'):
                return self.absolute_gain_cache
        own_dispersions = self.dispersions()
        root_dispersions = self.root().dispersions()
        gains = root_dispersions - own_dispersions
        if self.cache:
            self.absolute_gain_cache = gains
        return gains

    def local_gains(self):

        # Gains in dispersion relative to the parent node.
        # As above, only works for summation-type errors like SSME

        if self.cache:
            if hasattr(self, 'local_gain_cache'):
                return self.local_gain_cache
        if self.parent is not None:
            parent_dispersions = self.parent.dispersions()
        else:
            parent_dispersions = self.dispersions()
        own_dispersions = self.dispersions()
        gains = parent_dispersions - own_dispersions
        if self.cache:
            self.local_gain_cache = gains
        return gains

    def additive_gains(self):

        # What is the change in absolute values of medians of all features between parent node
        # and this node?

        # If you have a sample, and you have a number of nodes
        # FROM THE SAME TREE that this sample belongs to, then summing the additive gains of
        # all nodes produces a prediction for that sample.

        if self.cache:
            if hasattr(self, 'additive_cache'):
                return self.additive_cache
        if self.parent is not None:
            parent_medians = self.parent.medians()
        else:
            parent_medians = np.zeros(len(self.forest.output_features))
        own_medians = self.medians()
        additive = own_medians - parent_medians
        if self.cache:
            self.additive_cache = additive
        return additive

    def additive_mean_gains(self):

        # What is the change in absolute values of medians of all features between parent node
        # and this node?

        # What the hell is this method? If you have a sample, and you have a number of nodes
        # FROM THE SAME TREE that this sample belongs to, then summing the additive gains of
        # all nodes produces a prediction for that sample.

        if self.cache:
            if hasattr(self, 'additive_mean_cache'):
                return self.additive_mean_cache

        if self.parent is not None:
            parent_means = self.parent.means()
        else:
            parent_means = np.zeros(len(self.forest.output_features))
        own_means = self.means()
        additive = own_means - parent_means
        if self.cache:
            self.additive_mean_cache = additive
        return additive

    def feature_additive(self, feature):

        # Additive gains for a single feature. See additive_gains for explanation of additive gains

        fi = self.forest.truth_dictionary.feature_dictionary[feature]
        own_value = self.feature_median(feature)
        if self.parent is not None:
            parent_value = self.parent.feature_median(feature)
        else:
            parent_value = 0.
        return own_value - parent_value

    def feature_additive_mean(self, feature):

        # Additive gains using means instead of medians. Alternative prediction mode.
        # MAY produce superior results for features of intermediate sparsity.

        fi = self.forest.truth_dictionary.feature_dictionary[feature]
        own_value = self.feature_mean(feature)
        if self.parent is not None:
            parent_value = self.parent.feature_mean(feature)
        else:
            parent_value = 0.
        return own_value - parent_value

    def leaves(self, depth=None):

        # Obtains all leaves belonging to this node
        if depth is None:
            depth_limit = self.level + 1
        else:
            depth_limit = depth

        leaves = []
        if len(self.children) < 1 or self.level >= depth_limit:
            leaves.append(self)
        else:
            for child in self.children:
                leaves.extend(child.leaves(depth=depth))

        return leaves

    def stems(self):

        # Obtains all stems belonging to this node
        # (Stems are not roots and not leaves)

        stems = []
        for child in self.children:
            stems.extend(child.stems())
        for child in self.children:
            if len(child.children) > 0:
                stems.append(child)
        return stems

    def sister(self):

        # Obtains the sister node, if any

        if self.parent is None:
            return None
        else:
            for child in self.parent.children:
                if child is not self:
                    return child
            return None

    def descend(self, n):

        # All nodes no more than n levels down

        nodes = []
        if n > 0:
            for child in self.children:
                nodes.extend(child.descend(n - 1))
            if len(nodes) < 1:
                nodes.append(self)
        else:
            nodes.append(self)
        return nodes

    def root(self):

        # Ascend to tree root

        if self.parent is not None:
            return self.parent.root()
        else:
            return self

    def ancestors(self):

        # All anscestors of this node

        ancestors = []
        if self.parent is not None:
            ancestors.append(self.parent)
            ancestors.extend(self.parent.ancestors())
        return ancestors

    def nodes_by_level(self):

        # Levelizes this tree

        # (Eg: a list of lists, list[x] corresponds to all descendent nodes from this one that are x levels down)

        levels = [[self]]
        for child in self.children:
            child_levels = child.nodes_by_level()
            for i, child_level in enumerate(child_levels):
                if len(levels) < i + 2:
                    levels.append([])
                levels[i + 1].extend(child_level)
        return levels

    def plotting_representation(self):

        # Used for plotting individual trees, returns a nested list of proportions
        # of samples present

        total_width = sum([x.pop() for x in self.children])
        child_proportions = []
        for child in self.children:
            child_proportions.append(
                [float(child.pop()) / float(total_width), ])
            child_proportions[-1].append(child.plotting_representation())
        return child_proportions

    def sample_names(self):

        # Returns formal names (if any) for samples in this node

        return [self.forest.samples[i] for i in self.samples()]

    def feature(self):

        # Best guess at the "split feature" of this node, if any

        return self.filter.feature()

    def level(self, target):

        # Slices to a specific level of a given tree

        level_nodes = []
        if len(self.children) > 0:
            if self.level <= target:
                level_nodes.extend(self.children[0].level(target))
                level_nodes.extend(self.children[1].level(target))
        else:
            level_nodes.append(self)
        return level_nodes

    def depth(self, d=0):

        # How deep does this node go?

        for child in self.children:
            d = max(child.depth(d + 1), d)
        return d

    def trim(self, limit):

        if self.coefficient_of_determination() < limit:
            self.local_samples = self.samples()
            self.children = []

        for child in self.children:
            child.trim(limit)


    def predict_matrix_encoding(self,matrix):
        index_list = self.predict_matrix_indices(matrix)
        encoding = np.zeros((len(index_list),matrix.shape[0]),dtype=bool)
        for i,e in enumerate(index_list):
            encoding[i][e] = True
        return encoding

    def predict_matrix_indices(self, matrix, indices=None):
        if indices is None:
            indices = np.arange(matrix.shape[0])
        
        encoded_indices = []
        # Because I am an idiot and have to keep the same order as the main node org method, we have to do something dumb now
        swap_indices = []
        own_mask = self.filter.filter_matrix(matrix)
        
        if np.sum(own_mask) <= 0:
            return [indices[own_mask],]

        for child in self.children:
            child_indices = child.predict_matrix_indices(
                matrix[own_mask],indices = indices[own_mask])
            swap_indices.append(child_indices.pop())
            encoded_indices.extend(child_indices)

        encoded_indices.extend(swap_indices)
        encoded_indices.append(indices[own_mask])
        return encoded_indices


    def add_child_cluster(self, cluster, lr):

        # Keeps track of clusters that occur among child nodes.
        # Useful for calculating cluster-cluster tree distances
        # Experimental

        self.child_clusters[lr].append(cluster)
        if self.parent is not None:
            self.parent.add_child_cluster(cluster, self.lr)

    def set_split_cluster(self, cluster):

        # Sets the node split cluster

        self.split_cluster = cluster
        if self.parent is not None:
            self.parent.add_child_cluster(cluster, self.lr)
        for descendant in self.nodes():
            if not hasattr(descendant, 'split_cluster'):
                descendant.split_cluster = cluster

    def add_child_cluster(self, cluster, lr):

        # Adds a cluster to the child cluster information of this node

        self.child_clusters[lr].append(cluster)
        if self.parent is not None:
            self.parent.add_child_cluster(cluster, self.lr)

    def sample_cluster_means(self):

        # (roughly) provides the proportion of the samples in this node that belong to
        # each sample cluster. Allows us to test if node clusters and sample clusters have a
        # correspondence

        if self.cache:
            if hasattr(self, 'sample_cluster_cache'):
                return self.sample_cluster_cache

        sample_clusters = self.forest.sample_cluster_encoding.T[self.samples(
        )].T
        sample_cluster_means = np.mean(sample_clusters, axis=1)

        if self.cache:
            self.sample_cluster_cache = sample_cluster_means

        return sample_cluster_means

    def reset_cache(self):

        # Resets the cache values for various things.
        # Save memory, avoid errors when you add/remove output features

        possible_caches = [
            "absolute_gain_cache",
            "local_gain_cache",
            "additive_cache",
            "additive_mean_cache",
            "median_cache",
            "dispersion_cache",
            "mean_cache",
            "encoding_cache",
            "weighted_prediction_cache"
        ]

        for cache in possible_caches:
            try:
                delattr(self, cache)
            except:
                continue

    def derive_samples(self, samples):

        if self.local_samples is not None:
            self_copy = self.derived_copy()
            restricted = [s for s in self_copy.local_samples if s in samples]
            self_copy.local_samples = restricted
            return self_copy

        child_copies = []

        for child in self.children:
            child_copies.append(child.derive_samples(samples))

        if len(child_copies[0].samples()) < 1 or len(child_copies[1].samples()) < 1:
            self_copy = self.derived_copy()
            restricted = [s for s in self.samples() if s in samples]
            self_copy.local_samples = restricted
            return self_copy
        else:
            self_copy = self.derived_copy()
            self_copy.children = child_copies
            for child in self_copy.children:
                child.parent = self_copy
            return self_copy

    def derived_copy(self):
        self_copy = copy(self)
        self_copy.forest = None
        self_copy.tree = None
        self_copy.parent = None
        self_copy.children = []
        self_copy.filter = self.filter.derived_copy()
        self_copy.filter.node = self_copy
        self_copy.local_samples = deepcopy(self.local_samples)
        self_copy.child_clusters = deepcopy(self.child_clusters)
        self_copy.reset_cache()
        return self_copy


class Filter:

    def __init__(self, filter_json, node):
        try:
            if filter_json is None:
                self.node = node
                self.reduction = Reduction(None)
                self.split = 1.
                self.orientation = False
            else:
                self.node = node
                self.reduction = Reduction(filter_json['reduction'])
                self.split = filter_json['split']
                self.orientation = filter_json['orientation']
        except:
            print(filter_json)
            raise Exception

    def derived_copy(self):
        self_copy = copy(self)
        self_copy.node = None
        return self_copy

    def feature(self):
        if len(self.reduction.features) == 1:
            return self.reduction.features[0]
        else:
            raise Exception

    def filter(self, sample):
        sample_score = self.reduction.score_sample(sample)
        if self.orientation:
            return sample_score > self.split
        else:
            return sample_score <= self.split

    def filter_matrix(self, matrix):
        scores = self.reduction.score_matrix(matrix)
        if self.orientation:
            return scores > self.split
        else:
            return scores <= self.split


class Reduction:

    def __init__(self, reduction_json):
        if reduction_json is None:
            self.features = []
            self.scores = []
            self.means = []
        else:
            self.features = [f['index'] for f in reduction_json['features']]
            self.scores = reduction_json['scores']
            self.means = reduction_json['means']

    def score_sample(self, sample):
        compound_score = 0
        for feature, feature_score, feature_mean in zip(self.features, self.scores, self.means):
            compound_score += (sample[feature] - feature_mean) * feature_score
        return compound_score

    def score_matrix(self, matrix):
        compound_scores = np.zeros(matrix.shape[0])
        if len(self.features) > 0:
            compound_scores = np.sum(
                (matrix.T[self.features].T - self.means) * self.scores, axis=1)
        return compound_scores
