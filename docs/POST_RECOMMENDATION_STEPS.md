## Hệ thống Gợi ý Bài viết (User-Based CF)

Tài liệu này mô tả giải pháp gợi ý bài viết (Post Recommendation) dựa trên nguyên lý **User-Based Collaborative Filtering**: *"Gợi ý những bài viết mà những người giống bạn đã tương tác"*.

### Nguyên lý cốt lõi

1. **Leverage Existing Neighbors**: Tận dụng kết quả từ hệ thống gợi ý user (CF User-User) để lấy ra danh sách $k$ người dùng giống user hiện tại nhất ($Neighbors$).
2. **Collect Interactions**: Thu thập các bài viết mà tập $Neighbors$ này đã tương tác gần đây.
3. **Weighted Scoring**: Tính điểm bài viết dựa trên độ tương đồng của neighbor `sim(u, v)` và mức độ tương tác (Like/Share/Comment).

---

### Quy trình chi tiết (Pipeline)

#### 1. Lấy tập User tương đồng (Neighbors)
- **Input**: `user_id` hiện tại ($u$).
- **Source**: Lấy từ bảng kết quả `SimilarUsers` (đã được tính toán bởi hệ thống Periodic Job).
- **Logic**: Lấy Top-N neighbors có điểm similarity cao nhất (ví dụ: $N=50$).

#### 2. Candidate Generation (Tìm bài viết tiềm năng)
- Với mỗi user $v$ trong danh sách Neighbors:
  - Lấy danh sách các bài viết ($p$) mà $v$ đã tương tác trong $W$ ngày qua (ví dụ: 7-14 ngày).
  - Loại bỏ các bài viết quá cũ (nếu cần).

#### 3. Scoring (Tính điểm cơ bản)
Điểm của bài viết $p$ đối với user $u$ được tính tổng hợp từ tất cả neighbors đã tương tác với $p$:

$$ Score(u, p) = \sum_{v \in Neighbors, v \to p} \left( Similarity(u, v) \times Weight(Interaction_{v, p}) \right) $$

**Bảng trọng số tương tác ($Weight$) đề xuất:**
| Loại tương tác | Trọng số ($w$) | Lý do |
| :--- | :--- | :--- |
| **Share** | 3.0 | Hành động lan toả mạnh mẽ nhất |
| **Comment** | 2.0 | Thể hiện sự quan tâm sâu |
| **Like** | 1.0 | Tương tác nhẹ, phổ biến |
| **View** | 0.2 - 0.5 | Tương tác thụ động (nếu log được) |

#### 4. Filtering (Bộ lọc)
Sau khi có danh sách Candidates và điểm sơ bộ, áp dụng các bộ lọc cứng:
1. **Exclude Seen**: Bỏ các bài viết mà user $u$ **đã** view/like/comment (tránh gợi ý lại).
2. **Privacy/Block**: Bỏ bài viết từ các tác giả mà $u$ đã block hoặc interaction riêng tư không được phép thấy.
3. **Friend-Only**: Kiểm tra quyền truy cập của bài viết (nếu không phải public).

#### 5. Ranking & Time Decay (Xếp hạng & Yếu tố thời gian)
Điểm số cuối cùng nên bị giảm dần theo thời gian thực của bài viết để ưu tiên nội dung mới (Freshness).

$$ FinalScore(p) = Score(u, p) \times \frac{1}{(1 + \alpha \times AgeInDays)} $$

- $AgeInDays$: Tuổi của bài viết (tính từ lúc post đến hiện tại).
- $\alpha$: Hệ số suy giảm (ví dụ: 0.1).

---

### Ví dụ minh hoạ

**Giả sử:**
- User A đang cần gợi ý.
- User A tương đồng với User B (sim=0.8) và User C (sim=0.5).

**Hành vi Neighbors:**
- User B đã **Like** bài Post X.
- User C đã **Share** bài Post X.

**Tính điểm cho Post X:**
1. Đóng góp từ B: $0.8 \times 1.0 (Like) = 0.8$
2. Đóng góp từ C: $0.5 \times 3.0 (Share) = 1.5$
3. Tổng điểm cơ bản: $0.8 + 1.5 = 2.3$

Nếu Post X đã đăng được 2 ngày và User A chưa xem -> Gợi ý Post X cho A với score 2.3 (có thể decay một chút).

---

### Chiến lược Cold-Start (Khi chưa đủ data)

Hệ thống CF User-Based yêu cầu user phải có lịch sử tương tác để tìm neighbors.
- **User Mới hoàn toàn**:
  - Fallback sang thuật toán **Global Top Popular** (các bài nhiều like/share nhất hệ thống trong 24h qua).
  - Hoặc **Topic-based** (nếu user chọn sở thích lúc onboarding).
- **User ít tương tác**:
  - Mở rộng tập neighbors (giảm ngưỡng similarity).
