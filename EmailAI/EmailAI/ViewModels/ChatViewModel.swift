import SwiftUI

class ChatViewModel: ObservableObject {
    @Published var messages: [ChatMessageItem] = []
    @Published var inputText = ""
    @Published var isLoading = false
    @Published var errorMessage: String?

    func sendMessage(emails: [EmailItem], summaries: [SummaryItem]) {
        let text = inputText.trimmingCharacters(in: .whitespaces)
        guard !text.isEmpty else { return }

        let userMsg = ChatMessageItem(role: "user", content: text)
        messages.append(userMsg)
        inputText = ""
        errorMessage = nil
        isLoading = true

        Task {
            do {
                let context = buildContext(emails: emails, summaries: summaries)
                let apiMessages = messages.map { ["role": $0.role, "content": $0.content] }
                    + [["role": "user", "content": text]]

                let llm = LLMProviderFactory.shared.getSelectedProvider()
                let response = try await llm.chat(messages: apiMessages, systemPrompt: context)

                await MainActor.run {
                    let assistantMsg = ChatMessageItem(role: "assistant", content: response)
                    self.messages.append(assistantMsg)
                    self.isLoading = false
                }
            } catch {
                await MainActor.run {
                    self.errorMessage = error.localizedDescription
                    self.isLoading = false
                }
            }
        }
    }

    private func buildContext(emails: [EmailItem], summaries: [SummaryItem]) -> String {
        var parts: [String] = []

        if !summaries.isEmpty {
            parts.append("## Your Email Summaries")
            for s in summaries.prefix(10) {
                parts.append("- From: \(s.sender) | Subject: \(s.subject) | Summary: \(s.summaryPurpose)")
                if !s.actionItems.isEmpty {
                    parts.append("  Actions: \(s.actionItems.joined(separator: ", "))")
                }
            }
        }

        if !emails.isEmpty {
            parts.append("\n## Recent Emails")
            for e in emails.prefix(5) {
                let truncated = String(e.body.prefix(500))
                parts.append("- From: \(e.sender) | Subject: \(e.subject)\n  \(truncated)")
            }
        }

        if parts.isEmpty {
            return "You are an email assistant. No emails have been loaded yet."
        }

        return "You are an intelligent email assistant. Answer questions about the user's emails.\n\n" + parts.joined(separator: "\n")
    }
}
