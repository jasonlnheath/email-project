import XCTest
@testable import EmailAI

/// Tests for LLMProvider protocol and LLMProviderType enum
final class LLMProviderTests: XCTestCase {

    // MARK: - LLMProviderType Enum Tests

    func testLLMProviderTypeHasAnthropicCase() {
        let anthropic = LLMProviderType.anthropic
        XCTAssertEqual(anthropic.rawValue, "Anthropic")
        XCTAssertEqual(anthropic.id, "Anthropic")
    }

    func testLLMProviderTypeHasOpenAICase() {
        let openai = LLMProviderType.openai
        XCTAssertEqual(openai.rawValue, "OpenAI")
        XCTAssertEqual(openai.id, "OpenAI")
    }

    func testLLMProviderTypeIsIterable() {
        let allCases = LLMProviderType.allCases
        XCTAssertEqual(allCases.count, 2)
        XCTAssertTrue(allCases.contains(.anthropic))
        XCTAssertTrue(allCases.contains(.openai))
    }

    func testLLMProviderTypeIsIdentifiable() {
        let anthropic = LLMProviderType.anthropic
        XCTAssertEqual(anthropic.id, "Anthropic")
    }

    // MARK: - LLMProvider Protocol Conformance Tests

    func testAnthropicProviderConformsToLLMProvider() {
        let provider = AnthropicProvider()
        XCTAssertTrue(provider is LLMProvider)
    }

    func testOpenAIProviderConformsToLLMProvider() {
        let provider = OpenAIProvider(
            baseURL: "https://api.openai.com/v1",
            apiKey: "test-key",
            model: "gpt-4o"
        )
        XCTAssertTrue(provider is LLMProvider)
    }

    // MARK: - LLMProvider Chat Method Tests

    func testLLMProviderChatThrowsWithoutImplementation() async throws {
        // This test verifies the protocol exists and requires implementation
        // Once we have mock providers, we'll test actual functionality
        let provider = MockLLMProvider()

        let messages: [[String: String]] = [
            ["role": "user", "content": "Hello"]
        ]

        do {
            let response = try await provider.chat(messages: messages, systemPrompt: nil)
            XCTAssertEqual(response, "Mock response")
        } catch {
            XCTFail("Chat should not throw: \(error)")
        }
    }

    func testLLMProviderChatWithSystemPrompt() async throws {
        let provider = MockLLMProvider()

        let messages: [[String: String]] = [
            ["role": "user", "content": "Hello"]
        ]

        do {
            let response = try await provider.chat(messages: messages, systemPrompt: "You are a helpful assistant")
            XCTAssertEqual(response, "Mock response")
        } catch {
            XCTFail("Chat with system prompt should not throw: \(error)")
        }
    }

    // MARK: - LLMProvider SummarizeEmail Method Tests

    func testLLMProviderSummarizeEmail() async throws {
        let provider = MockLLMProvider()

        do {
            let result = try await provider.summarizeEmail(
                subject: "Test Subject",
                sender: "test@example.com",
                body: "Test email body"
            )

            XCTAssertEqual(result.summaryPurpose, "Test summary")
            XCTAssertEqual(result.keyEntities.count, 0)
            XCTAssertEqual(result.actionItems.count, 0)
            XCTAssertEqual(result.sentiment, "neutral")
        } catch {
            XCTFail("Summarize email should not throw: \(error)")
        }
    }

    func testLLMProviderSummarizeEmailWithComplexContent() async throws {
        let provider = MockLLMProvider()

        do {
            let result = try await provider.summarizeEmail(
                subject: "Meeting Tomorrow",
                sender: "john@company.com",
                body: "Let's meet tomorrow at 2pm to discuss the Q4 roadmap. Action items: prepare slides, send calendar invite."
            )

            XCTAssertEqual(result.summaryPurpose, "Test summary")
        } catch {
            XCTFail("Summarize should handle complex content: \(error)")
        }
    }
}

// MARK: - Mock LLM Provider for Testing

actor MockLLMProvider: LLMProvider {
    func chat(messages: [[String: String]], systemPrompt: String?) async throws -> String {
        return "Mock response"
    }

    func summarizeEmail(subject: String, sender: String, body: String) async throws -> SummarizeResult {
        return SummarizeResult(
            summaryPurpose: "Test summary",
            keyEntities: [],
            actionItems: [],
            sentiment: "neutral"
        )
    }
}
