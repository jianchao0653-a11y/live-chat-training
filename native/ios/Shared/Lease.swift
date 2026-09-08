import Foundation

struct InsertionLease: Codable {
    let lease_id: String
    let secret: String
    let expires_at: Double
    let draft: String
    let person_name: String
    var endpoint: String?
    func valid(at now: Date = Date()) -> Bool {
        expires_at > now.timeIntervalSince1970 * 1000 && !draft.isEmpty && !secret.isEmpty
    }
}

enum LensError: LocalizedError {
    case message(String)
    var errorDescription: String? { if case .message(let text) = self { return text }; return nil }
}

enum EndpointPolicy {
    static func root(_ text: String) throws -> URL {
        guard let url = URL(string: text), url.scheme == "https", url.host != nil,
              url.user == nil, url.password == nil, url.query == nil, url.fragment == nil,
              url.path.isEmpty || url.path == "/" else {
            throw LensError.message("请输入可信 HTTPS 服务根地址")
        }
        return url
    }
}

enum LeaseStore {
    static let byteLimit = 64_000
    static func file() throws -> URL {
        guard let group = Bundle.main.object(forInfoDictionaryKey: "LensAppGroup") as? String,
              let folder = FileManager.default.containerURL(forSecurityApplicationGroupIdentifier: group) else {
            throw LensError.message("共享容器不可用，请检查签名与完全访问设置")
        }
        return folder.appendingPathComponent("approved-lease.json")
    }
    static func save(_ lease: InsertionLease) throws {
        guard lease.valid() else { throw LensError.message("草稿授权已过期") }
        let url = try file()
        let data = try JSONEncoder().encode(lease)
        guard data.count < byteLimit else { throw LensError.message("草稿文件过大") }
        try data.write(to: url, options: [.atomic, .completeFileProtection])
        var protected = url
        var values = URLResourceValues(); values.isExcludedFromBackup = true
        try protected.setResourceValues(values)
    }
    static func load() throws -> InsertionLease {
        let url = try file()
        let data: Data
        do { data = try BoundedData.readFile(url, limit: byteLimit) }
        catch { try? clear(); throw error }
        let lease = try JSONDecoder().decode(InsertionLease.self, from: data)
        guard lease.valid() else { try? clear(); throw LensError.message("草稿已过期，请回主 App 重新准备") }
        return lease
    }
    static func clear() throws { let url = try file(); if FileManager.default.fileExists(atPath: url.path) { try FileManager.default.removeItem(at: url) } }
}

enum BoundedData {
    // Exclusive limits, including decoded bytes when HTTP compression is used.
    static func collect<S: AsyncSequence>(_ bytes: S, limit: Int, expectedLength: Int64 = -1) async throws -> Data where S.Element == UInt8 {
        guard limit > 0, expectedLength < Int64(limit) else { throw LensError.message("服务响应过大") }
        var data = Data()
        for try await byte in bytes {
            guard data.count < limit - 1 else { throw LensError.message("服务响应过大") }
            data.append(byte)
        }
        return data
    }
    static func readFile(_ url: URL, limit: Int) throws -> Data {
        guard limit > 0 else { throw LensError.message("草稿文件无效") }
        let handle = try FileHandle(forReadingFrom: url)
        defer { try? handle.close() }
        var data = Data()
        while let chunk = try handle.read(upToCount: min(16_384, limit - data.count)), !chunk.isEmpty {
            data.append(chunk)
            guard data.count < limit else { throw LensError.message("草稿文件过大") }
        }
        return data
    }
}

final class NoRedirect: NSObject, URLSessionTaskDelegate {
    func urlSession(_ session: URLSession, task: URLSessionTask, willPerformHTTPRedirection response: HTTPURLResponse, newRequest request: URLRequest, completionHandler: @escaping (URLRequest?) -> Void) { completionHandler(nil) }
}

enum NativeHTTP {
    static func call(endpoint: String, path: String, token: String = "", body: [String: Any]? = nil) async throws -> [String: Any] {
        let root = try EndpointPolicy.root(endpoint)
        let url = root.appendingPathComponent("api/native/" + path)
        var request = URLRequest(url: url); request.timeoutInterval = 120
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if !token.isEmpty { request.setValue("Bearer " + token, forHTTPHeaderField: "Authorization") }
        if let body { request.httpMethod = "POST"; request.httpBody = try JSONSerialization.data(withJSONObject: body) }
        let config = URLSessionConfiguration.ephemeral; config.urlCache = nil; config.timeoutIntervalForResource = 120
        let session = URLSession(configuration: config, delegate: NoRedirect(), delegateQueue: nil)
        defer { session.invalidateAndCancel() }
        let (bytes, response) = try await session.bytes(for: request)
        let data = try await BoundedData.collect(bytes, limit: 2_000_000, expectedLength: response.expectedContentLength)
        guard let http = response as? HTTPURLResponse,
              let object = try JSONSerialization.jsonObject(with: data) as? [String: Any] else { throw LensError.message("服务响应无效") }
        guard (200...299).contains(http.statusCode) else { throw LensError.message(object["error"] as? String ?? "请求失败") }
        return object
    }
}
