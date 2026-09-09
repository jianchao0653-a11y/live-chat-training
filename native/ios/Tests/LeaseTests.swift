import XCTest
final class LeaseTests: XCTestCase {
    final class Counter { var reads = 0 }
    struct Bytes: AsyncSequence, AsyncIteratorProtocol {
        typealias Element = UInt8
        let counter: Counter
        var remaining: Int
        func makeAsyncIterator() -> Bytes { self }
        mutating func next() async throws -> UInt8? {
            guard remaining > 0 else { return nil }
            remaining -= 1; counter.reads += 1; return 65
        }
    }
    func testUnboundedResponseStopsReadingAtLimit() async throws {
        let counter = Counter()
        do { _ = try await BoundedData.collect(Bytes(counter: counter, remaining: 10_000_000), limit: 64); XCTFail("oversize accepted") }
        catch { XCTAssertEqual(counter.reads, 64) }
        let valid = try await BoundedData.collect(Bytes(counter: Counter(), remaining: 63), limit: 64)
        XCTAssertEqual(valid.count, 63)
    }
    func testDeclaredOversizeRejectedBeforeReading() async {
        let counter = Counter()
        do { _ = try await BoundedData.collect(Bytes(counter: counter, remaining: 100), limit: 64, expectedLength: 64); XCTFail("oversize accepted") }
        catch { XCTAssertEqual(counter.reads, 0) }
    }
    func testFileLimitAndValidLeaseRoundTrip() throws {
        let url = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: url) }
        let lease = InsertionLease(lease_id:"synthetic",secret:"s",expires_at:Date().timeIntervalSince1970 * 1000 + 30_000,draft:"合成草稿",person_name:"合成人物")
        try JSONEncoder().encode(lease).write(to: url)
        let restored = try JSONDecoder().decode(InsertionLease.self, from: BoundedData.readFile(url, limit: LeaseStore.byteLimit))
        XCTAssertEqual(restored.draft, lease.draft)
        try Data(repeating: 65, count: LeaseStore.byteLimit).write(to: url)
        XCTAssertThrowsError(try BoundedData.readFile(url, limit: LeaseStore.byteLimit))
        try Data(repeating: 65, count: LeaseStore.byteLimit - 1).write(to: url)
        XCTAssertEqual(try BoundedData.readFile(url, limit: LeaseStore.byteLimit).count, LeaseStore.byteLimit - 1)
    }
    func testTransportRejectsUntrustedEndpoints() {
        for value in ["http://example.com", "https://user:pass@example.com", "https://example.com/path", "https://example.com?token=x"] { XCTAssertThrowsError(try EndpointPolicy.root(value)) }
        XCTAssertNoThrow(try EndpointPolicy.root("https://example.com:4317"))
    }
    func testLeaseExpiryAndMissingAuthority() {
        let now = Date(timeIntervalSince1970: 100)
        XCTAssertTrue(InsertionLease(lease_id:"x",secret:"s",expires_at:100001,draft:"合成文字",person_name:"合成人物").valid(at:now))
        XCTAssertFalse(InsertionLease(lease_id:"x",secret:"s",expires_at:100000,draft:"合成文字",person_name:"合成人物").valid(at:now))
        XCTAssertFalse(InsertionLease(lease_id:"x",secret:"",expires_at:130000,draft:"合成文字",person_name:"合成人物").valid(at:now))
    }
}
