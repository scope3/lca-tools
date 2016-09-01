"""
This module contains utility functions for building fragments. It should probably be called 'fragment_builder.py'
but that name was taken.
"""

from lcatools.interact import pick_one, cyoa, ifinput, pick_list, _pick_list, pick_one_or
from lcatools.foreground.manager import ForegroundManager
from lcatools.foreground.fragment_flows import LcFragment
from lcatools.entities import LcFlow, LcQuantity
from lcatools.exchanges import Exchange, comp_dir
from lcatools.catalog import ExchangeRef


def select_archive(F):
    F.show_all()
    ch1 = input('Search which catalog? or blank to search all loaded catalogs')
    if len(ch1) == 0:
        index = None
    else:
        try:
            index = int(ch1)
        except ValueError:
            index = F._catalog.get_index(ch1)
    F.current_archive = index
    return index


class ForegroundBuilder(ForegroundManager):

    def __init__(self, *args, **kwargs):
        super(ForegroundBuilder, self).__init__(*args, **kwargs)
        self.current_archive = None

    def find_flow(self, name, index=None, elementary=False):
        if name is None:
            name = input('Enter flow name search string: ')
        res = self.search(index, 'flow', Name=name, show=False)
        if elementary is not None:
            res = list(filter(lambda x: self.db.is_elementary(x.entity()) == elementary, res))
        pick = pick_one(res)
        print('Picked: %s' % pick)
        return pick

    def create_fragment(self, parent=None):
        ch = cyoa('(N)ew flow or (S)earch for flow? ', 'ns')
        if ch == 'n':
            flow = self.new_flow()
        elif ch == 's':
            index = self.current_archive or select_archive(self)
            elem = {'i': False,
                    'e': True,
                    'a': None}[cyoa('(I)ntermediate, (E)lementary, or (A)ll flows? ', 'aei', 'I').lower()]
            flow = self.find_flow(None, index=index, elementary=elem)
            if flow is None:
                return None
            flow = flow.entity()
        else:
            raise ValueError
        print('Creating fragment with flow %s' % flow)
        direction = {'i': 'Input', 'o': 'Output'}[cyoa('flow is (I)nput or (O)utput?', 'IO').lower()]
        comment = ifinput('Enter comment: ', '')
        if parent is None:
            # direction reversed for UX! user inputs direction w.r.t. fragment, not w.r.t. parent
            frag = self.new_fragment(flow, comp_dir(direction), Comment=comment)
        else:
            frag = self[0].add_child_fragment_flow(parent, flow, direction, Comment=comment)
        return frag

    def add_child(self, frag):
        return self.create_fragment(parent=frag)

    def find_termination(self, ref, index=None, direction=None):
        if isinstance(ref, LcFragment):
            if index is None:
                index = self.current_archive or select_archive(self)
            terms = self._catalog.terminate_fragment(index, ref)
        elif isinstance(ref, Exchange):
            if index is None:
                index = self.current_archive or select_archive(self)
            terms = self._catalog.terminate_flow(self.ref(index, ref.flow), comp_dir(ref.direction))
        else:
            if direction is None:
                direction = {'i': 'Input', 'o': 'Output'}[cyoa('(I)nput or (O)utput?', 'IO').lower()]
            terms = self._catalog.terminate_flow(ref, direction)
        pick = pick_one(terms)
        print('Picked: %s' % pick)
        return pick

    def terminate_by_search(self, frag, index=None):
        print('%s' % frag)
        print('Search for termination.')
        string = input('Enter search term: ')
        return pick_one(self.search(index, 'p', Name=string, show=False))

    def add_termination(self, frag, term, scenario=None):
        if isinstance(term, ExchangeRef):
            print('Terminating from exchange\n')
            frag.term_from_exch(term, scenario=scenario)
        else:
            print('Terminating from process ref\n')
            frag.terminate(term, scenario=scenario)
        self.build_child_flows(frag, background_children=True)

    def auto_terminate(self, frag, index=None, scenario=None):
        if scenario is None and not frag.term.is_null:
            return  # nothing to do-- (ecoinvent) already terminated by exchange
        ex = self.find_termination(frag, index=index)
        if ex is None:
            ex = self.terminate_by_search(frag, index=index)
        if ex is not None:
            self.add_termination(frag, ex, scenario=scenario)
        else:
            print('Not terminated.')

    def foreground(self, frag, index=None):
        self.fragment_to_foreground(frag)
        self.auto_terminate(frag, index=index)

    def curate_stages(self, frag, stage_names=None):
        def _recurse_stages(f):
            stages = [f['StageName']]
            for m in self.child_flows(f):
                stages.extend(_recurse_stages(m))
            return stages

        if stage_names is None:
            stage_names = set(_recurse_stages(frag))

        print("Select stage for %s \n(or enter '' to quit)" % frag)
        ch = pick_one_or(sorted(stage_names), default=frag['StageName'])
        if ch == '':
            return
        if ch not in stage_names:
            stage_names.add(ch)
        frag['StageName'] = ch
        for c in self.child_flows(frag):
            self.curate_stages(c, stage_names=stage_names)

    def background_scenario(self, scenario, index=None):
        if index is None:
            index = self.current_archive or select_archive(self)
        for bg in self[0].fragments(background=True):
            print('\nfragment %s' % bg)
            if scenario in bg.terminations():
                print('Terminated to %s' % bg.termination(scenario).term_node)
            ch = cyoa('(K)eep current or (S)earch for termination? ', 'ks', 'k')
            if ch == 's':
                p_ref = self.terminate_by_search(bg, index=index)
                if p_ref is not None:
                    bg.terminate(p_ref, scenario=scenario)
