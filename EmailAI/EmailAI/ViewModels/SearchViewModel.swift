import SwiftUI

class SearchViewModel: ObservableObject {
    @Published var searchText = ""
    @Published var results: [EmailItem] = []

    func search(in emails: [EmailItem]) {
        guard !searchText.isEmpty else {
            results = []
            return
        }
        let lower = searchText.lowercased()
        results = emails.filter { email in
            email.subject.lowercased().contains(lower) ||
            email.sender.lowercased().contains(lower) ||
            email.body.lowercased().contains(lower)
        }
    }
}
