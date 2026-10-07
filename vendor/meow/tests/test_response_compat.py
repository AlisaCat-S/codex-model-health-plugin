"""Offline regression for missing final Responses output; no model requests."""
import json
import unittest
from gpt56_vnext.protocol import parse_stream
from gpt56_vnext.security import SecretGuard
from gpt56_vnext.errors import RequestError
from gpt56_vnext.normalizers import normalize_answer


def created(identity='a'):
    return {'type': 'response.created', 'response': {'id': identity}}


def delta(value='France'):
    return {'type': 'response.output_text.delta', 'delta': value}


def final(output=(), identity='a', **extra):
    response = {'id': identity, 'status': 'completed', **extra}
    if output != ():
        response['output'] = output
    return {'type': 'response.completed', 'response': response}


def output(value):
    return [{'type': 'message', 'content': [{'type': 'output_text', 'text': value}]}]


def cases():
    yield 'missing', [created(), delta(), final()], 'France'
    yield 'empty-container', [created(), delta(), final([])], 'France'
    yield 'final-wins', [created(), delta(), final(output('Japan'))], 'Japan'
    for value in ('', '  '):
        yield 'explicit-empty', [created(), delta(), final(output(value))], 'invalid_answer'
    for value in ([{'type': 'reasoning'}], [{'type': 'function_call'}], [{'content': [{'type': 'text', 'text': 'Japan'}]}]):
        yield 'nontext', [created(), delta(), final(value)], 'invalid_answer'
    yield 'no-delta', [created(), final([])], 'invalid_answer'
    yield 'done-only', [created(), {'type': 'response.output_text.done', 'text': 'France'}, final([])], 'invalid_answer'
    yield 'empty-delta', [created(), delta(''), final([])], 'invalid_answer'
    yield 'no-completion', [created(), delta()], 'truncated_stream'
    yield 'done-not-completion', [created(), delta(), '[DONE]'], 'truncated_stream'
    for event in ('response.refusal.delta', 'response.refusal.done'):
        yield event, [created(), delta(), {'type': event, 'refusal': 'No'}, final([])], 'response_refused'
    yield 'final-refusal', [created(), delta(), final([{'content': [{'type': 'refusal', 'refusal': 'No'}]}])], 'response_refused'
    for event, detail, expected in (
        ('response.failed', {'error': {'code': 'server_error'}}, 'upstream_response_failed'),
        ('response.incomplete', {'incomplete_details': {'reason': 'max_output_tokens'}}, 'response_token_limit'),
    ):
        failed = {'type': event, 'response': {'id': 'a', **detail}}
        yield event, [created(), delta(), failed, '[DONE]'], expected
        yield event + '-then-completed', [created(), delta(), failed, final([])], expected
    for extra in ({'error': {'code': 'server_error'}}, {'incomplete_details': {'reason': 'max_output_tokens'}}):
        yield 'contradictory-completion', [created(), delta(), final([], **extra)], 'invalid_answer'
    yield 'previous-not-reused', [created(), final(output('old')), created('b'), final([], 'b')], 'invalid_answer'
    yield 'last-own-delta', [created(), final(output('old')), created('b'), delta('new'), final([], 'b')], 'new'
    yield 'null', [created(), delta(), final(None)], 'invalid_stream'
    yield 'duplicate', [created(), delta(), final([]), final([])], 'invalid_stream'
    yield 'secret', [created(), delta('synthetic-secret'), final([])], 'credential_echo'
    yield 'length', [created(), delta('a' * 4097), final([])], 'invalid_answer'


def run_cases(test, parser=parse_stream, guard=SecretGuard, error=RequestError):
    for name, events, expected in cases():
        with test.subTest(name=name, parser=parser.__module__):
            stream = ''.join('data: ' + (e if isinstance(e, str) else json.dumps(e)) + '\n\n' for e in events)
            try:
                result = parser(stream, 'gpt', guard(['synthetic-secret']))
                answer = result['answer']
                normalized = normalize_answer(answer, {'id': 'exact_trimmed_casefold', 'parameters': {'max_length': 4096}})
                actual = 'invalid_answer' if normalized == '__INVALID_OUTPUT__' else answer
            except error as exc:
                actual = exc.code
            test.assertEqual(actual, expected)


class ResponsesCompatibilityTests(unittest.TestCase):
    def test_missing_output_boundaries(self):
        run_cases(self)


if __name__ == '__main__':
    unittest.main()
