import SwiftUI

struct ChatView: View {
    @EnvironmentObject var emailListVM: EmailListViewModel
    @EnvironmentObject var chatVM: ChatViewModel

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                // Message list
                ScrollViewReader { proxy in
                    ScrollView {
                        LazyVStack(spacing: 12) {
                            ForEach(chatVM.messages) { message in
                                MessageBubble(message: message)
                                    .id(message.id)
                            }
                        }
                        .padding()
                    }
                    .onChange(of: chatVM.messages.count) { _ in
                        if let lastMessage = chatVM.messages.last {
                            withAnimation {
                                proxy.scrollTo(lastMessage.id, anchor: .bottom)
                            }
                        }
                    }
                }

                Divider()

                // Error message
                if let error = chatVM.errorMessage {
                    Text(error)
                        .font(.caption)
                        .foregroundStyle(.red)
                        .padding(.horizontal)
                }

                // Input bar
                HStack(spacing: 12) {
                    TextField("Ask about your emails...", text: $chatVM.inputText, axis: .vertical)
                        .textFieldStyle(.plain)
                        .lineLimit(1...5)
                        .padding(12)
                        .background(Color(.systemGray6))
                        .clipShape(RoundedRectangle(cornerRadius: 20))

                    Button(action: sendMessage) {
                        Image(systemName: "arrow.up.circle.fill")
                            .font(.title)
                            .foregroundStyle(.blue)
                    }
                    .disabled(chatVM.inputText.trimmingCharacters(in: .whitespaces).isEmpty || chatVM.isLoading)
                }
                .padding(.horizontal)
                .padding(.vertical, 8)
            }
            .navigationTitle("Chat")
        }
    }

    private func sendMessage() {
        chatVM.sendMessage(emails: emailListVM.emails, summaries: emailListVM.summaries)
    }
}

struct MessageBubble: View {
    let message: ChatMessageItem

    var body: some View {
        HStack {
            if message.role == "user" { Spacer() }

            VStack(alignment: message.role == "user" ? .trailing : .leading, spacing: 4) {
                Text(message.content)
                    .padding(12)
                    .foregroundStyle(message.role == "user" ? .white : .primary)
                    .background(
                        message.role == "user"
                        ? Color.blue
                        : Color(.systemGray6)
                    )
                    .clipShape(RoundedRectangle(cornerRadius: 16))
                    .textSelection(.enabled)

                Text(message.timestamp, style: .time)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }

            if message.role == "assistant" { Spacer() }
        }
    }
}

struct ChatView_Previews: PreviewProvider {
    static var previews: some View {
        ChatView()
            .environmentObject(EmailListViewModel())
            .environmentObject(ChatViewModel())
    }
}
