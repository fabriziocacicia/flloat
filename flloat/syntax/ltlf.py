from abc import abstractmethod
from typing import Set

from flloat.base.Formula import Formula, CommutativeBinaryOperator, AtomicFormula, BinaryOperator
from flloat.base.Symbol import Symbol
from flloat.base.Symbols import Symbols
from flloat.base.convertible import ImpliesDeltaConvertible, EquivalenceDeltaConvertible, ConvertibleFormula, \
    BaseConvertibleFormula
from flloat.base.nnf import NNF, NotNNF, DualBinaryOperatorNNF, DualUnaryOperatorNNF
from flloat.base.truths import Truth, NotTruth, OrTruth, AndTruth
from flloat.flloat import DFAOTF, to_automaton
from flloat.semantics.ldlf import FiniteTrace, FiniteTraceTruth
from flloat.semantics.pl import PLInterpretation, PLTrueInterpretation, PLFalseInterpretation
from flloat.syntax.ldlf import Delta
from flloat.syntax.pl import PLTrue, PLFalse, PLAnd, PLOr, PLAtomic


class LTLfTruth(Truth):
    @abstractmethod
    def truth(self, i: FiniteTrace, pos: int):
        raise NotImplementedError


class LTLfFormula(Formula, LTLfTruth, NNF, Delta):

    def delta(self, i: PLInterpretation, epsilon=False):
        f = self.to_nnf()
        d = f._delta(i, epsilon)
        if epsilon:
            # By definition, if epsilon=True, then the result must be either PLTrue or PLFalse
            # Now, the output is a Propositional Formula with only PLTrue or PLFalse as atomics
            # Hence, we just evaluate the formula with a dummy PLInterpretation
            d = PLTrue() if d.truth(PLFalseInterpretation()) else PLFalse()
        return d

    @abstractmethod
    def _delta(self, i: PLInterpretation, epsilon=False):
        """apply delta function, assuming that 'self' is a LDLf formula in Negative Normal Form"""
        raise NotImplementedError

    def __repr__(self):
        return self.__str__()

    def to_automaton(self, labels:Set[Symbol]=None, on_the_fly=False, determinize=False, minimize=True):
        if on_the_fly:
            return DFAOTF(self)
        else:
            new_labels = labels.union({Symbol(Symbols.LTLf_LAST.value)})
            return to_automaton(self, new_labels, determinize, minimize)


class LTLfCommBinaryOperator(LTLfFormula, CommutativeBinaryOperator):
    pass

class LTLfTemporalFormula(LTLfFormula, FiniteTraceTruth):
    pass


class LTLfAtomic(LTLfFormula, AtomicFormula):

    def __init__(self, a:PLAtomic):
        super().__init__(a.s)
        self.a = a

    def __str__(self):
        return AtomicFormula.__str__(self)


    def _members(self):
        return (LTLfAtomic, self.a)

    def to_nnf(self):
        return self

    def negate(self):
        return LTLfNot(LTLfAtomic(self.a))

    def _delta(self, i:PLInterpretation, epsilon=False):
        if epsilon:
            return PLFalse()
        return PLTrue() if self.a.truth(i) else PLFalse()

    def truth(self, i: FiniteTrace, pos: int):
        return self.a.truth(i.get(pos))

    def find_labels(self):
        return self.a.find_labels()


class LTLfTrue(LTLfAtomic):
    def __init__(self):
        super().__init__(PLTrue())


class LTLfFalse(LTLfAtomic):
    def __init__(self):
        super().__init__(PLFalse())


class LTLfNot(LTLfFormula, NotTruth, NotNNF):

    def _delta(self, i: PLInterpretation, epsilon=False):
        if isinstance(self.f, LTLfAtomic):
            return PLTrue() if self.f._delta(i, epsilon)==PLFalse() else PLFalse()
        else:
            # the formula must be in NNF form!!!
            raise Exception

class LTLfAnd(LTLfCommBinaryOperator, AndTruth, DualBinaryOperatorNNF):

    def _delta(self, i:PLInterpretation, epsilon=False):
        return PLAnd([f._delta(i, epsilon) for f in self.formulas])


class LTLfOr(LTLfCommBinaryOperator, OrTruth, DualBinaryOperatorNNF):

    def _delta(self, i:PLInterpretation, epsilon=False):
        return PLOr([f._delta(i, epsilon) for f in self.formulas])


class LTLfImplies(ImpliesDeltaConvertible, LTLfFormula):
    And = LTLfAnd
    Or = LTLfOr
    Not = LTLfNot

class LTLfEquivalence(EquivalenceDeltaConvertible, LTLfCommBinaryOperator):
    And = LTLfAnd
    Or = LTLfOr
    Not = LTLfNot


class LTLfNext(DualUnaryOperatorNNF, LTLfTemporalFormula):
    operator_symbol = "X"
    Not = LTLfNot

    def truth(self, i: FiniteTrace, pos: int):
        return pos < i.last() and self.f.truth(i, pos + 1)

    def _delta(self, i: PLInterpretation, epsilon=False):
        if epsilon:
            return PLFalse()
        else:
            return self.f if not Symbol(Symbols.LTLf_LAST.value) in i else PLFalse()


class LTLfWeakNext(DualUnaryOperatorNNF, ConvertibleFormula, LTLfTemporalFormula):
    operator_symbol = Symbols.WEAK_NEXT.value
    Not = LTLfNot

    def _convert(self):
        return LTLfNot(LTLfNext(LTLfNot(self.f)))

    def truth(self, i: FiniteTrace, pos: int):
        return self._convert().truth(i, pos)

    def _delta(self, i: PLInterpretation, epsilon=False):
        if epsilon:
            return PLTrue()
        else:
            return self.f if not Symbol(Symbols.LTLf_LAST.value) in i else PLTrue()


class LTLfUntil(LTLfTemporalFormula, BinaryOperator):
    operator_symbol = "U"

    def to_nnf(self):
        return LTLfUntil([f.to_nnf() for f in self.formulas])

    def negate(self):
        return LTLfRelease([LTLfNot(f) for f in self.formulas])

    def truth(self, i: FiniteTrace, pos: int):
        f1 = self.formulas[0]
        f2 = LTLfUntil(self.formulas[1:]) if len(self.formulas)>2 else self.formulas[1]
        return any(f2.truth(i, j) and all(f1.truth(i, k) for k in range(pos, j)) for j in range(pos, i.last()+1))

    def _delta(self, i:PLInterpretation, epsilon=False):
        f1 = self.formulas[0]
        f2 = LTLfUntil(self.formulas[1:]) if len(self.formulas) > 2 else self.formulas[1]
        return PLOr([
            f2._delta(i, epsilon),
            PLAnd([
                f1._delta(i, epsilon),
                LTLfNext(self)._delta(i, epsilon)
            ])
        ])


class LTLfEventually(DualUnaryOperatorNNF, BaseConvertibleFormula, LTLfTemporalFormula):
    operator_symbol = "F"
    Not = LTLfNot

    def _convert(self):
        return LTLfUntil([LTLfTrue(), self.f])

    def _delta(self, i:PLInterpretation, epsilon=False):
        return PLOr([self.f._delta(i, epsilon), LTLfNext(self)._delta(i, epsilon)])


class LTLfAlways(DualUnaryOperatorNNF,  BaseConvertibleFormula, LTLfTemporalFormula):
    operator_symbol = "G"
    Not = LTLfNot

    def _convert(self):
        return LTLfNot(LTLfEventually(LTLfNot(self.f)))

    def _delta(self, i:PLInterpretation, epsilon=False):
        return PLAnd([self.f._delta(i, epsilon), LTLfWeakNext(self)._delta(i, epsilon)])

class LTLfRelease(DualBinaryOperatorNNF, BaseConvertibleFormula, LTLfTemporalFormula):
    operator_symbol = "R"
    Dual = LTLfUntil

    def _convert(self):
        return LTLfNot(LTLfUntil([LTLfNot(f) for f in self.formulas]))

    def _delta(self, i:PLInterpretation, epsilon=False):
        f1 = self.formulas[0]
        f2 = LTLfRelease(self.formulas[1:]) if len(self.formulas) > 2 else self.formulas[1]
        return PLAnd([
            f2._delta(i, epsilon),
            PLOr([
                f1._delta(i, epsilon),
                LTLfNext(self)._delta(i, epsilon)
            ])
        ])


LTLfAnd.Dual = LTLfOr
LTLfOr.Dual = LTLfAnd

LTLfNext.Dual = LTLfWeakNext
LTLfWeakNext.Dual = LTLfNext

LTLfEventually.Dual = LTLfAlways
LTLfAlways.Dual = LTLfEventually
