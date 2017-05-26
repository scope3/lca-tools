class ProductFlow(object):
    """
    Class for storing foreground-relevant information about a single matched row-and-column in the interior matrix.

    """
    def __init__(self, index, flow, process):
        """
        Initialize a row+column in the technology matrix.  Each row corresponds to a reference exchange in the database,
        and thus represents a particular process generating / consuming a particular flow.  A ProductFlow entry is
        akin to a fragment termination.

        inbound_ev is the exchange value of the reference flow, which is divided into the exchange values of the child
        flows.  It has the convention Output = positive, so if the reference exchange is an input, the inbound_ev is
        negated.  Similarly, the exchange values of matrix entries made with ProductFlow parents need to be implemented
        as Input = positive, with outputs negated.  This is to satisfy the make-use equation e.g. V - U' in Suh 2010
        or whichever it was.

        :param flow: the LcFlow entity that represents the commodity (term_flow in the fragment sense)
        :param process: the termination of the parent node's exchange (term_node). None is equivalent to a
        cutoff flow or elementary flow (distinction is left to a compartment manager).  If non-null, the process must
        possess a reference exchange with the same flow or the graph traversal may be curtailed.
        """
        self._index = index
        self._flow = flow
        self._process = process
        self._direction = None

        self._hash = (flow.external_ref, None)
        self._inbound_ev = 1.0

        if process is None:
            raise TypeError('No termination? should be a cutoff.')

        if len([x for x in process.reference_entity if x.flow == flow]) == 0:
            # still a cutoff- raise a flag but not an error
            print('NoMatchingReference: Flow: %s, Termination: %s' % (flow.external_ref, process.external_ref))
        else:
            self._hash = (flow.external_ref, process.external_ref)
            ref_exch = process.reference(flow)
            self._direction = ref_exch.direction
            self._inbound_ev = ref_exch.value
            if self._inbound_ev is None:
                print('None inbound ev! using 1.0. f:%s t:%s' % (flow, process))
                self._inbound_ev = 1.0
            elif self._inbound_ev == 0:
                raise ZeroDivisionError('No inbound EV for f:%s t:%s' % (flow.external_ref,
                                                                         process.external_ref))
            if self._direction == 'Input':
                self._inbound_ev *= -1

    def __eq__(self, other):
        """
        shortcut-- allow comparisons without dummy creation
        :param other:
        :return:
        """
        return hash(self) == hash(other)
        # if not isinstance(other, ProductFlow):
        #    return False
        # return self.flow == other.flow and self.process == other.process

    def __hash__(self):
        return hash(self._hash)

    def adjust_ev(self, value):
        """
        Compensate recorded inbound exchange value if the process is found to depend on its own reference flow.
        Assumption is that the flow is already sign-corrected (i.e. inbound_ev is positive-output, adjustment value
        is positive-input, so new inbound_ev is difference
        :param value:
        :return:
        """
        if value == self._inbound_ev:
            print('Ignoring unitary self-dependency')
        else:
            self._inbound_ev -= value

    @property
    def index(self):
        return self._index

    @property
    def key(self):
        """
        Product flow key is (uuid of reference flow, uuid of process)
        :return:
        """
        return self._hash

    @property
    def flow(self):
        return self._flow

    @property
    def process(self):
        return self._process

    @property
    def direction(self):
        return self._direction

    @property
    def inbound_ev(self):
        return self._inbound_ev

    @property
    def _dirn(self):
        return {'Input': '<',
                'Output': '>'}[self.direction]

    def __str__(self):
        return '%s:=%s=%s' % (self._process, self._dirn, self._flow)

    def table_label(self):
        return '%s (%s) [%s]' % (self._flow['Name'], self._flow.unit(), self._process['SpatialScope'])
